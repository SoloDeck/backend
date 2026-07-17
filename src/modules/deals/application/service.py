"""Deals application service."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.facade import AIFacade
from src.ai.lead_qualifier.scoring import (
    compute_readiness,
    compute_win_likelihood,
    level_from_score,
    normalize_price_range,
)
from src.modules.deals.domain.aggregates.deal_aggregate import DealAggregate
from src.modules.deals.domain.entities.deal import Deal
from src.modules.deals.domain.value_objects.ai_confidence import AIConfidence
from src.modules.deals.domain.value_objects.deal_stage import (
    STAGE_TRANSITIONS,
    TERMINAL_STAGES,
    DealStage,
)
from src.modules.deals.infrastructure.repository import DealsRepository
from src.modules.deals.schemas.request import DealRequest, DealStageRequest, PublicIntakeRequest
from src.shared.exceptions.domain import (
    BusinessRuleError,
    InvalidStateTransitionError,
    NotFoundError,
)
from src.shared.rate_limit import FixedWindowRateLimiter

log = structlog.get_logger(__name__)

# Basic per-link guard for the public, unauthenticated intake form. Process-local;
# a generous window so legitimate submissions are unaffected while a flood of
# automated posts to a single share link is throttled (returns HTTP 429).
_public_intake_limiter = FixedWindowRateLimiter(max_requests=20, window_seconds=60)

# Fields the lead_qualifier prompt's schema requires (see src/ai/lead_qualifier/
# prompts/prompts.txt) but that _parse_output never validates the LLM actually
# returned — logged here so an incomplete AI response is visible, not silent.
_EXPECTED_QUALIFICATION_KEYS = frozenset(
    {
        "project_type",
        "budget_signal",
        "timeline_signal",
        "urgency_signal",
        "red_flags",
        "next_step",
        "detected_signals",
        "suggested_actions",
        "price_range_min",
        "price_range_max",
    }
)


@dataclass
class DealsService:
    db: AsyncSession
    ai_facade: AIFacade | None = None
    repo: DealsRepository | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = DealsRepository(self.db)

    async def _get_deal(self, user_id: uuid.UUID, deal_id: uuid.UUID):  # type: ignore[return]
        deal = await self.repo.get_by_id(deal_id, user_id)
        if deal is None:
            raise NotFoundError(f"Deal {deal_id} not found")
        return deal

    async def _get_intake(
        self,
        user_id: uuid.UUID,
        intake_id: uuid.UUID,
    ):
        intake = await self.repo.get_intake_by_id(intake_id, user_id)

        if intake is None:
            raise NotFoundError(f"Deal intake {intake_id} not found")

        return intake

    async def create(self, user_id: uuid.UUID, payload: DealRequest):  # type: ignore[return]
        client = await self.repo.get_client_by_id(payload.client_id, user_id)
        if client is None:
            raise NotFoundError(f"Client {payload.client_id} not found")
        return await self.repo.create(
            owner_user_id=user_id,
            client_id=payload.client_id,
            title=payload.title,
            stage=payload.stage,
            source=payload.source,
            estimated_value=payload.estimated_value,
            actual_value=payload.actual_value,
            currency=payload.currency,
            notes=payload.notes,
            desired_timeline=payload.desired_timeline,
            project_type=payload.project_type,
            service_category=payload.service_category,
            pricing_tier=payload.pricing_tier,
        )

    async def create_public_intake(self, share_token: str, payload: PublicIntakeRequest):
        """Capture a lead submitted through the owner's public intake link.

        No authentication: the owner is resolved solely from the hard-to-guess
        `share_token`. Creates a minimal prospect Client, a `new_lead` Deal (so it
        surfaces in the owner's pipeline / GET /deals) and a DealIntake holding the
        raw inquiry for later AI qualification (Package 3 — no scoring here).
        """
        # Throttle by the raw token first so both valid and invalid links are
        # rate-limited (basic abuse guard) before any DB work.
        _public_intake_limiter.check(share_token)

        owner = await self.repo.get_owner_by_intake_token(share_token)
        if owner is None:
            raise NotFoundError("Intake form not found or link is invalid")

        # Deduplicate: reuse an existing client when both name and phone match.
        client = None
        if payload.phone:
            client = await self.repo.find_client_by_name_and_phone(
                owner.id, payload.name, payload.phone
            )
        if client is None:
            client = await self.repo.create_client(
                owner_user_id=owner.id,
                type="individual",
                name=payload.name,
                email=payload.email,
                phone=payload.phone,
                status="prospect",
            )
        deal = await self.repo.create(
            owner_user_id=owner.id,
            client_id=client.id,
            title=payload.project_name or f"Intake — {payload.name}",
            stage="new_lead",
            source="inbound",
            currency=owner.currency,
        )
        intake = await self.repo.create_intake(
            owner_user_id=owner.id,
            client_id=client.id,
            # Gắn phiếu vào ĐÚNG deal vừa tạo. Thiếu dòng này là khách gửi form lần hai
            # thì deal cũ bị chấm điểm (và báo giá) bằng brief của dự án mới.  #Huynh
            deal_id=deal.id,
            inquiry_text=payload.inquiry_text or "",
            estimated_budget=payload.estimated_budget,
            desired_timeline=payload.desired_timeline,
            source="inbound",
        )

        # Báo cho freelancer biết có khách mới. Thiếu bước này thì deal nằm im trong cột
        # "Deal Mới" cho tới khi freelancer tự mở ra xem — deal nóng để vài ngày là mất
        # khách, mà cả điểm mạnh của sản phẩm là "AI chấm điểm NGAY khi khách gửi form".
        #
        # Ghi vào cùng transaction với deal: hoặc cả hai cùng có, hoặc cả hai cùng không.
        # Không thể có deal mà không có thông báo.  #Huynh
        from src.modules.notifications.application.service import NotificationService

        await NotificationService(db=self.db).notify_intake_submitted(
            owner_user_id=owner.id,
            deal_id=deal.id,
            client_name=payload.name,
            project_name=payload.project_name,
        )

        from src.workers.ai_jobs.tasks import qualify_deal_async_by_id

        qualify_deal_async_by_id.delay(str(owner.id), str(deal.id))

        return intake

    async def list_all(
        self,
        user_id: uuid.UUID,
        title: str | None = None,
        stage: str | None = None,
        client_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list, int]:
        return await self.repo.list_all(
            user_id, title=title, stage=stage, client_id=client_id, page=page, page_size=page_size
        )

    async def list_intakes(
        self, user_id: uuid.UUID, page: int = 1, page_size: int = 20
    ) -> tuple[list, int]:
        return await self.repo.list_intakes(user_id, page=page, page_size=page_size)

    async def get_intake(self, user_id: uuid.UUID, intake_id: uuid.UUID):
        intake = await self._get_intake(user_id, intake_id)
        return intake

    async def get_one(self, user_id: uuid.UUID, deal_id: uuid.UUID):  # type: ignore[return]
        return await self._get_deal(user_id, deal_id)

    async def update(self, user_id: uuid.UUID, deal_id: uuid.UUID, payload: DealRequest):  # type: ignore[return]
        deal = await self._get_deal(user_id, deal_id)
        for field in (
            "title",
            "source",
            "estimated_value",
            "actual_value",
            "currency",
            "notes",
            "desired_timeline",
            "project_type",
            "service_category",
            "pricing_tier",
        ):
            value = getattr(payload, field, None)
            if value is not None:
                setattr(deal, field, value)
        return await self.repo.save(deal)

    async def delete(self, user_id: uuid.UUID, deal_id: uuid.UUID) -> None:
        deal = await self._get_deal(user_id, deal_id)
        deal.deleted_at = datetime.now(UTC)
        await self.repo.save(deal)

    async def transition_stage(
        self, user_id: uuid.UUID, deal_id: uuid.UUID, payload: DealStageRequest
    ):  # type: ignore[return]
        deal = await self._get_deal(user_id, deal_id)
        try:
            current = DealStage(deal.stage)
            target = DealStage(payload.stage)
        except ValueError as exc:
            raise BusinessRuleError("Invalid deal stage") from exc
        if target not in STAGE_TRANSITIONS.get(current, frozenset()):
            raise InvalidStateTransitionError("deal", deal.stage, payload.stage)
        if target == DealStage.ACTIVE and not await self.repo.has_accepted_proposal(
            deal_id, user_id
        ):
            raise BusinessRuleError("Transitioning to active requires an accepted proposal")
        if target == DealStage.COMPLETED_AND_BILLED and not await self.repo.has_invoice(
            deal_id, user_id
        ):
            raise BusinessRuleError(
                "Transitioning to completed_and_billed requires a linked invoice"
            )
        deal.stage = payload.stage
        if target in TERMINAL_STAGES and hasattr(deal, "closed_at"):
            deal.closed_at = datetime.now(UTC)
            await self.repo.cancel_pending_reminders(deal_id, user_id)
        saved = await self.repo.save(deal)
        # Design decision #3 (Phase 24): a deal entering `active` auto-provisions a
        # linked Project. We call ProjectService directly (in the same session /
        # transaction) and idempotently — re-running a transition never duplicates
        # the project. Project invariants stay owned by the projects domain.
        if target == DealStage.ACTIVE:
            from src.modules.projects.application.service import ProjectService

            await ProjectService(db=self.db).get_or_create_for_deal(
                deal_id, user_id, name=deal.title
            )
        return saved

    async def _run_ai_qualification(self, deal_model, inquiry_context: str) -> dict:
        """Run AI lead qualification against inquiry_context and persist scores on deal_model."""
        result = await self.ai_facade.qualify_lead(  # type: ignore[union-attr]
            inquiry_text=inquiry_context,
            user_can_use_ai=True,  # TODO: get from subscriptions
        )

        missing_keys = sorted(
            key for key in _EXPECTED_QUALIFICATION_KEYS if result.get(key) is None
        )
        if missing_keys:
            log.warning(
                "deals.qualify_deal.incomplete_ai_output",
                deal_id=str(deal_model.id),
                missing_keys=missing_keys,
            )

        # Trước đây điểm chỉ là bảng tra ba nấc {"HOT": 80, "WARM": 50, "COLD": 20} —
        # AI không hề chấm điểm, nên deal 20 triệu và deal 700 nghìn đều ra đúng 50/100.
        # Giờ AI chấm TỪNG tiêu chí, backend cộng tổng (không giao phép cộng cho LLM),
        # và nhãn HOT/WARM/COLD suy ra TỪ điểm nên không bao giờ mâu thuẫn với nó.  #Huynh
        score, readiness_breakdown = compute_readiness(result.get("score_breakdown"))
        lead_level = level_from_score(score)
        result["suggested_lead_score"] = lead_level  # ghi đè nhãn model tự đoán
        result["score_breakdown"] = readiness_breakdown

        _confidence_map = {
            "HOT": AIConfidence.high(),
            "WARM": AIConfidence.medium(),
            "COLD": AIConfidence.low(),
        }
        confidence = _confidence_map.get(lead_level, AIConfidence.medium())
        reasoning = str(result.get("reasoning", ""))
        # Trước ghi "gemma-4-31b-it" — SAI. Model chạy thật là llama-4-scout (xem
        # lead_qualifier/chain.py). Ghi sai model là ghi sai bằng chứng.  #Huynh
        model_version = "meta-llama/llama-4-scout-17b-16e-instruct"

        # Khả năng chốt deal — tính bằng CODE từ CHÍNH bảng phân rã ở trên, không hỏi AI
        # và không dò chuỗi trong câu văn của model.  #Huynh
        points = {item["key"]: item["points"] for item in readiness_breakdown}
        result["win_likelihood"] = compute_win_likelihood(
            budget_points=points.get("budget", 0),
            timeline_points=points.get("timeline", 0),
            detail_points=points.get("detail", 0),
            estimated_value=deal_model.estimated_value,
            price_range_min=result.get("price_range_min"),
            source=deal_model.source,
        )

        deal_domain = Deal(
            id=deal_model.id,
            owner_user_id=deal_model.owner_user_id,
            client_id=deal_model.client_id,
            title=deal_model.title,
            stage=DealStage(deal_model.stage),
            value=None,
            source=deal_model.source,
            expected_close_date=None,
            ai_score=deal_model.ai_qualification_score,
            ai_confidence=None,
            ai_recommendation=deal_model.ai_qualification_recommendation,
            closed_at=deal_model.closed_at,
            created_at=deal_model.created_at,
            updated_at=deal_model.updated_at,
            deleted_at=deal_model.deleted_at,
        )
        aggregate = DealAggregate(deal=deal_domain)
        lead_score = aggregate.score_lead(
            score=score,
            confidence=confidence.value,
            reasoning=reasoning,
            model_version=model_version,
        )

        detected_signals_raw = result.get("detected_signals")
        detected_signals = (
            [s if isinstance(s, dict) else s.model_dump() for s in detected_signals_raw]
            if detected_signals_raw
            else None
        )

        # Lưu CẢ PHẦN CHỨNG MINH vào lịch sử, không chỉ con số. `breakdown` (bảng căn cứ
        # chấm điểm) trước đây chỉ nằm ở localStorage của trình duyệt — đổi máy là mất.
        await self.repo.create_lead_score(
            id=lead_score.id,
            deal_id=lead_score.deal_id,
            score=lead_score.score,
            confidence=lead_score.confidence.value,
            reasoning=lead_score.reasoning,
            model_version=lead_score.model_version,
            generated_at=lead_score.generated_at,
            project_type=result.get("project_type"),
            budget_signal=result.get("budget_signal"),
            timeline_signal=result.get("timeline_signal"),
            urgency_signal=result.get("urgency_signal"),
            red_flags=result.get("red_flags"),
            breakdown=result.get("score_breakdown"),
            next_step=result.get("next_step"),
            detected_signals=detected_signals,
            prompt_version=result.get("prompt_version"),
        )

        deal_model.ai_qualification_score = lead_score.score
        deal_model.ai_qualification_confidence = lead_score.confidence.value
        deal_model.ai_qualification_recommendation = aggregate.deal.ai_recommendation
        deal_model.ai_qualification_reasoning = reasoning
        deal_model.ai_qualification_project_type = result.get("project_type")
        deal_model.ai_qualification_budget_signal = result.get("budget_signal")
        deal_model.ai_qualification_timeline_signal = result.get("timeline_signal")
        deal_model.ai_qualification_urgency_signal = result.get("urgency_signal")
        deal_model.ai_qualification_red_flags = result.get("red_flags")
        deal_model.ai_qualification_next_step = result.get("next_step")
        deal_model.ai_qualification_detected_signals = detected_signals
        deal_model.ai_qualification_suggested_actions = result.get("suggested_actions")
        # Model hay viết tắt "30 triệu" thành 30 → giao diện in ra "30 ₫". Chữa ở đây.
        price_low, price_high = normalize_price_range(
            result.get("price_range_min"), result.get("price_range_max")
        )
        result["price_range_min"] = price_low
        result["price_range_max"] = price_high
        deal_model.ai_qualification_price_range_min = price_low or None
        deal_model.ai_qualification_price_range_max = price_high or None
        await self.repo.save(deal_model)

        return {
            **result,
            "detected_signals": detected_signals,
            "ai_qualification_score": score,
            "ai_qualification_recommendation": aggregate.deal.ai_recommendation,
        }

    async def list_qualifications(self, user_id: uuid.UUID, deal_id: uuid.UUID) -> list:
        """Lịch sử chấm điểm của deal — mới nhất trước.

        Mỗi lần chấm là một dòng RIÊNG, không ghi đè. Sửa deal rồi chấm lại thì bản cũ vẫn
        còn nguyên để đối chiếu — đó là lý do có bảng lịch sử.  #Huynh
        """
        await self._get_deal(user_id, deal_id)  # 404 nếu deal không phải của người này
        return await self.repo.list_lead_scores(deal_id, user_id)

    async def qualify_deal(
        self,
        user_id: uuid.UUID,
        deal_id: uuid.UUID,
    ):
        deal_model = await self._get_deal(user_id, deal_id)

        if not self.ai_facade:
            raise RuntimeError("AIFacade not initialized")

        # Tách bạch AI NÓI GÌ và FREELANCER TỰ NHẬP GÌ.
        #
        # Trước đây tất cả gộp thành một danh sách phẳng, trong đó có dòng
        # "Estimated value: 200000 VND" — mà đó là ô "Giá trị dự kiến" do FREELANCER tự
        # điền lúc tạo deal, KHÔNG PHẢI khách báo giá. AI đọc thấy con số thì tưởng khách
        # đã nêu ngân sách và chấm 20/25 "khách cung cấp giá trị cụ thể", trong khi khách
        # chưa hề nói gì về tiền. Nhãn dữ liệu mập mờ thì AI có giỏi mấy cũng chấm sai.
        #
        # Giờ chia hai khối rõ ràng, và prompt bắt buộc chỉ chấm ngân sách/thời gian dựa
        # trên khối "KHÁCH HÀNG NÓI GÌ".  #Huynh
        intake = await self.repo.get_intake_for_deal(deal_model.id, deal_model.client_id, user_id)

        own: list[str] = [f"- Tên dự án: {deal_model.title}"]
        if deal_model.source:
            own.append(f"- Nguồn deal: {deal_model.source}")
        if deal_model.project_type:
            own.append(f"- Loại dự án: {deal_model.project_type}")
        if deal_model.service_category:
            own.append(f"- Nhóm dịch vụ: {deal_model.service_category}")
        if deal_model.notes:
            own.append(f"- Ghi chú nội bộ: {deal_model.notes}")
        if deal_model.estimated_value:
            own.append(
                f"- Giá trị dự kiến (FREELANCER TỰ ƯỚC, KHÔNG PHẢI KHÁCH BÁO): "
                f"{deal_model.estimated_value} {deal_model.currency}"
            )

        said: list[str] = []
        client_budget = getattr(intake, "estimated_budget", None) if intake else None
        client_timeline = getattr(intake, "desired_timeline", None) if intake else None
        if intake is not None and intake.inquiry_text:
            said.append(f"- Nguyên văn yêu cầu: {intake.inquiry_text}")

        # Chữ bóc từ file khách gửi kèm (brief dự án PDF).
        #
        # Đây là mảnh còn thiếu quan trọng nhất: deal tạo TAY luôn mất trọn 25 điểm ngân
        # sách vì luật chấm điểm chỉ tính những gì KHÁCH nói — mà khách thì "chưa nói gì"
        # (ô "Giá trị dự kiến" là freelancer tự nhập). Nên deal tự tạo gần như luôn COLD.
        #
        # Nhưng khách GỬI HẲN MỘT FILE BRIEF thì đó CHÍNH LÀ LỜI KHÁCH. Đưa vào đây, AI
        # đọc được yêu cầu thật, ngân sách thật, deadline thật.  #Huynh
        attachments = await self.repo.list_attachments_with_text(deal_model.id, user_id)
        for att in attachments:
            said.append(f"- Nội dung file khách gửi ({att.filename}):")
            said.append(att.extracted_text or "")
        if client_budget:
            said.append(f"- Ngân sách khách nêu: {client_budget}")
        if client_timeline:
            said.append(f"- Thời gian khách muốn: {client_timeline}")
        if deal_model.desired_timeline:
            said.append(f"- Thời hạn ghi nhận được: {deal_model.desired_timeline}")

        inquiry_context = "\n".join(
            [
                "## THÔNG TIN FREELANCER TỰ NHẬP (không phải lời khách)",
                *own,
                "",
                "## KHÁCH HÀNG NÓI GÌ",
                *(said or ["- (Khách chưa cung cấp thông tin nào)"]),
            ]
        )

        return await self._run_ai_qualification(deal_model, inquiry_context)
