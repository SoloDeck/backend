"""Proposals application service."""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.proposal_generator.application.render import ProposalPdfRenderer
from src.ai.proposal_generator.pricing import (
    build_anchor,
    compute_quote,
    parse_deadline,
)
from src.modules.deals.infrastructure.repository import DealsRepository
from src.modules.proposals.application.pdf_content import build_proposal_document
from src.modules.proposals.infrastructure.repository import ProposalsRepository
from src.modules.proposals.schemas.request import ProposalRequest
from src.modules.subscriptions.application.ai_usage import AiUsageService
from src.shared.events.bus import event_bus
from src.shared.exceptions.domain import (
    BusinessRuleError,
    InvalidStateTransitionError,
    NotFoundError,
)

# Hạn hiệu lực mặc định. Chỉ là ĐIỂM XUẤT PHÁT — freelancer sửa được ngay trên tờ báo giá,
# và lựa chọn của họ nằm ở `content["valid_until"]`.
#
# Đủ ngắn để giá không bị treo vô thời hạn (sáu tháng sau khách quay lại đòi đúng con số cũ
# là chuyện có thật), nhưng ngắn quá thì vướng cuối tuần: gửi chiều thứ Năm, hết hạn thứ Hai
# — khách chỉ còn ~2 ngày làm việc để hỏi lại, xin duyệt ngân sách, so với báo giá khác. Ai
# đổi con số này nên cân nhắc điều đó.  #Huynh
DEFAULT_VALID_DAYS = 4


def _vn_date(value: date) -> str:
    """Ngày kiểu Việt: 31/07/2026. ISO (2026-07-31) là kiểu của máy, không phải của khách."""
    return value.strftime("%d/%m/%Y")


def _parse_iso_date(value: object) -> date | None:
    """Đọc ngày freelancer đã đặt. Rác thì trả None để rơi về mặc định, không nổ.  #Huynh"""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


_VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"sent"}),
    "sent": frozenset({"accepted", "rejected", "expired"}),
    "accepted": frozenset(),
    "rejected": frozenset(),
    "expired": frozenset(),
    "superseded": frozenset(),
}


@dataclass
class ProposalsService:
    db: AsyncSession
    repo: ProposalsRepository | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = ProposalsRepository(self.db)

    async def _get_proposal(self, user_id: uuid.UUID, proposal_id: uuid.UUID):  # type: ignore[return]
        proposal = await self.repo.get_by_id(proposal_id, user_id)
        if proposal is None:
            raise NotFoundError(f"Proposal {proposal_id} not found")
        return proposal

    async def create(  # type: ignore[return]
        self,
        user_id: uuid.UUID,
        payload: ProposalRequest,
        *,
        ai_generated: bool = False,
    ):
        deal = await self.repo.get_deal(payload.deal_id)
        if deal is None or deal.owner_user_id != user_id:
            raise NotFoundError(f"Deal {payload.deal_id} not found")
        version_number = await self.repo.count_by_deal(payload.deal_id) + 1
        return await self.repo.create(
            deal_id=payload.deal_id,
            owner_user_id=user_id,
            version_number=version_number,
            status=payload.status,
            content=payload.content,
            ai_generated=ai_generated,
        )

    async def list_all(
        self,
        user_id: uuid.UUID,
        status: str | None = None,
        deal_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list, int]:
        return await self.repo.list_all(
            user_id, status=status, deal_id=deal_id, page=page, page_size=page_size
        )

    async def get_one(self, user_id: uuid.UUID, proposal_id: uuid.UUID):  # type: ignore[return]
        return await self._get_proposal(user_id, proposal_id)

    async def update(self, user_id: uuid.UUID, proposal_id: uuid.UUID, payload: ProposalRequest):  # type: ignore[return]
        proposal = await self._get_proposal(user_id, proposal_id)
        if proposal.status != "draft":
            raise BusinessRuleError(
                f"Proposal content can only be edited in draft status "
                f"(current status: '{proposal.status}')"
            )
        if payload.content:
            proposal.content = payload.content
        return await self.repo.save(proposal)

    async def delete(self, user_id: uuid.UUID, proposal_id: uuid.UUID) -> None:
        proposal = await self._get_proposal(user_id, proposal_id)
        await self.repo.delete(proposal)

    async def set_price(self, user_id: uuid.UUID, proposal_id: uuid.UUID, price: Decimal):  # type: ignore[return]
        """Freelancer chốt giá. Ghi vào báo giá VÀ vào deal.

        Ghi cả hai chỗ vì hai mục đích khác nhau:
        - `proposal.content["pricing_detail"]["final_price"]` -> in ra bản gửi khách.
        - `deal.estimated_value` -> để báo cáo doanh thu dự kiến và phễu bán hàng đúng.

        CHƯA CHỐT GIÁ THÌ KHÔNG GỬI ĐƯỢC BÁO GIÁ (xem `transition_status`). Gửi cho khách
        một bản báo giá ghi "87 – 162 triệu" là tự bắn vào chân mình.  #Huynh
        """
        proposal = await self._get_proposal(user_id, proposal_id)
        if proposal.status != "draft":
            raise BusinessRuleError(
                f"Chỉ chốt được giá khi báo giá còn ở trạng thái nháp "
                f"(hiện tại: '{proposal.status}')"
            )

        content = dict(proposal.content or {})
        detail = dict(content.get("pricing_detail") or {})

        detail["final_price"] = int(price)
        # Ghi lại việc giá chốt có nằm ngoài khoảng đề xuất không — để sau này còn đối chiếu
        # xem bộ định giá đề xuất có sát thực tế không.
        low, high = detail.get("range_min"), detail.get("range_max")
        if low and high:
            detail["final_outside_range"] = not (low <= int(price) <= high)

        content["pricing_detail"] = detail
        content["pricing"] = f"{int(price):,} ₫".replace(",", ".")
        proposal.content = content

        deal = await self.repo.get_deal(proposal.deal_id)
        if deal is not None and deal.owner_user_id == user_id:
            deal.estimated_value = price

        return await self.repo.save(proposal)

    async def _apply_pricing(
        self, content: dict, deal, user_id: uuid.UUID, client_budget_text: str | None
    ) -> dict:
        """Tính giá và nhét khối `pricing` vào nội dung báo giá.

        Đây là nơi ranh giới AI/code hiện ra rõ nhất:

        - AI vừa trả về `complexity`, `scale`, `line_item_weights` — KHÔNG một đồng nào.
        - Hàm này neo vào GIÁ THẬT freelancer đã chốt, nhân hệ số, ra khoảng giá.
        - Freelancer mới là người CHỐT con số cuối cùng (PATCH /proposals/{id}/price).

        Dùng chung cho CẢ HAI đường sinh báo giá. Tách riêng vì trước đây hai đường tự làm
        lấy, và cùng một deal gọi hai endpoint khác nhau lại ra hai kết quả khác nhau.  #Huynh
        """
        if deal is None:
            return content

        # Dùng thẳng DealsRepository thay vì chép lại câu SQL sang ProposalsRepository:
        # "thế nào là một deal tương đương" phải có ĐÚNG MỘT định nghĩa. Chép sang đây là
        # ngày nào đó hai bên lệch nhau, và mốc neo giá âm thầm sai.  #Huynh
        same_category, any_category = await DealsRepository(db=self.db).comparable_deal_values(
            user_id, deal.service_category
        )

        anchor = build_anchor(
            same_category_values=same_category,
            any_category_values=any_category,
            market_low=_to_decimal(deal.ai_qualification_price_range_min),
            market_high=_to_decimal(deal.ai_qualification_price_range_max),
        )

        if anchor is None:
            # Không neo được vào đâu cả: chưa chốt deal nào, và deal này cũng chưa được AI
            # chấm điểm (nên không có khoảng giá thị trường). NÓI THẲNG thay vì bịa một con
            # số — bản báo giá 0 ₫ trước đây tệ, nhưng một con số bịa còn tệ hơn.  #Huynh
            content["pricing"] = (
                "Chưa đủ dữ liệu để đề xuất giá. Hãy bấm “Đánh giá deal” để AI ước lượng "
                "khoảng giá thị trường, hoặc nhập giá bạn muốn chào."
            )
            content["pricing_detail"] = None
            return content

        # DÙNG LẠI thứ bộ chấm điểm đã trích ra.
        #
        # Khi chấm điểm, AI đã bóc sẵn "Ngân sách khách nêu: 120 triệu" và "Bàn giao trước
        # 30/09/2026" từ mô tả/file PDF, rồi lưu vào `ai_qualification_*_signal`. Không đọc
        # lại chúng ở đây là vứt đi công đã làm — và thực tế đã vứt: deal có ghi rõ ngân
        # sách 120 triệu trong ghi chú mà bộ định giá vẫn báo "khách chưa nêu ngân sách",
        # nên không hề cảnh báo khi giá đề xuất vọt lên gấp đôi túi tiền khách.  #Huynh
        deadline_text = " ".join(
            filter(
                None,
                [
                    deal.ai_qualification_timeline_signal,
                    deal.desired_timeline,
                    content.get("timeline"),
                    deal.notes,
                ],
            )
        )
        client_budget = _parse_money(client_budget_text) or _parse_money(
            deal.ai_qualification_budget_signal
        )

        quote = compute_quote(
            anchor=anchor,
            complexity=content.get("complexity") or "normal",
            complexity_reason=content.get("complexity_reason") or "",
            scale=content.get("scale") or "normal",
            scale_reason=content.get("scale_reason") or "",
            deadline=parse_deadline(deadline_text),
            weights=content.get("line_item_weights") or [],
            client_budget=client_budget,
        )

        detail = quote.to_dict()
        content["pricing_detail"] = detail
        content["pricing"] = (
            f"{detail['range_min']:,} ₫ – {detail['range_max']:,} ₫ "
            f"(đề xuất: {detail['suggested']:,} ₫)"
        ).replace(",", ".")

        # Ba trường thô của AI đã được nấu thành `pricing_detail`. Giữ lại trong nội dung
        # gửi khách là rác — khách không cần biết hệ số nội bộ của ta.
        for key in (
            "complexity",
            "complexity_reason",
            "scale",
            "scale_reason",
            "line_item_weights",
        ):
            content.pop(key, None)

        return content

    async def generate_content(self, user_id: uuid.UUID, proposal_id: uuid.UUID, ai_facade):  # type: ignore[return]
        proposal = await self._get_proposal(user_id, proposal_id)
        if proposal.status != "draft":
            raise BusinessRuleError(
                f"AI generation is only available for draft proposals "
                f"(current status: '{proposal.status}')"
            )

        # Cổng AI: kiểm tra gói (402), kiểm tra hạn mức tháng (429), ghi nhận lượt dùng.
        # Xem src/modules/subscriptions/application/ai_usage.py  #Huynh
        await AiUsageService(db=self.db).consume(user_id)

        sub = await self.repo.get_subscription(user_id)
        plan = await self.repo.get_plan(sub.plan_id) if sub else None
        user_can_use_ai = bool(plan and plan.can_use_ai)

        deal = await self.repo.get_deal(proposal.deal_id)
        client = await self.repo.get_client(deal.client_id) if deal else None
        user = await self.repo.get_user(user_id)

        budget = None
        if deal and deal.estimated_value is not None:
            budget = f"{deal.estimated_value} {deal.currency or 'VND'}"

        company_name = None
        if client and getattr(client, "type", None) == "company":
            company_name = client.name

        # Cả BA đường sinh báo giá (/ai-generate, /generate-from-deal, /{id}/generate) đều
        # phải thấy CÙNG một bộ dữ liệu — nếu không thì cùng một deal, gọi endpoint khác
        # nhau lại ra báo giá khác nhau.  #Huynh
        intake = None
        if deal and deal.client_id:
            intake = await self.repo.get_intake_for_deal(deal.id, deal.client_id, user_id)

        content = await ai_facade.generate_proposal(
            deal_data={
                "title": deal.title if deal else "",
                "stage": deal.stage if deal else "",
                "notes": deal.notes if deal else "",
                "project_type": deal.project_type if deal else None,
                "service_category": deal.service_category if deal else None,
                "pricing_tier": deal.pricing_tier if deal else None,
                "budget": budget,
                "client_inquiry": getattr(intake, "inquiry_text", None) if intake else None,
                "client_budget": getattr(intake, "estimated_budget", None) if intake else None,
                "client_timeline": (getattr(intake, "desired_timeline", None) if intake else None)
                or (deal.desired_timeline if deal else None),
            },
            client_data={
                "name": client.name if client else "",
                "company_name": company_name,
                "email": client.email if client else "",
            },
            user_profile={
                "name": user.full_name if user else "",
                "email": user.email if user else "",
            },
            template=None,
            user_can_use_ai=user_can_use_ai,
        )
        await AiUsageService(db=self.db).record_cost(
            user_id,
            ai_module="proposal_generator",
            usage=ai_facade.last_usage("proposal_generator"),
        )

        content = await self._apply_pricing(
            content,
            deal,
            user_id,
            (getattr(intake, "estimated_budget", None) if intake else None),
        )

        proposal.content = content
        proposal.ai_generated = True
        return await self.repo.save(proposal)

    async def generate_from_deal(self, user_id: uuid.UUID, deal_id: uuid.UUID, ai_facade):  # type: ignore[return]
        deal = await self.repo.get_deal(deal_id)
        if deal is None or deal.owner_user_id != user_id:
            raise NotFoundError(f"Deal {deal_id} not found")

        # Cổng AI: kiểm tra gói (402), kiểm tra hạn mức tháng (429), ghi nhận lượt dùng.
        # Xem src/modules/subscriptions/application/ai_usage.py  #Huynh
        await AiUsageService(db=self.db).consume(user_id)

        sub = await self.repo.get_subscription(user_id)
        plan = await self.repo.get_plan(sub.plan_id) if sub else None
        user_can_use_ai = bool(plan and plan.can_use_ai)

        client = await self.repo.get_client(deal.client_id) if deal.client_id else None
        user = await self.repo.get_user(user_id)

        budget = None
        if deal.estimated_value is not None:
            budget = f"{deal.estimated_value} {deal.currency or 'VND'}"

        company_name = None
        if client and getattr(client, "type", None) == "company":
            company_name = client.name

        # Nguyên văn yêu cầu khách viết trong Biểu mẫu tiếp nhận. Đây là nguồn tin GIÀU
        # NHẤT về dự án, nhưng trước đây AI soạn báo giá KHÔNG hề được đọc — chỉ
        # lead_qualifier đọc. Hậu quả: khách mô tả cả đoạn mà báo giá vẫn mỏng dính, vì
        # thứ duy nhất AI thấy là ghi chú nội bộ của freelancer.  #Huynh
        intake = None
        if deal.client_id:
            intake = await self.repo.get_intake_for_deal(deal.id, deal.client_id, user_id)

        content = await ai_facade.generate_proposal(
            deal_data={
                "title": deal.title,
                "stage": deal.stage,
                "notes": deal.notes,
                "project_type": deal.project_type,
                "service_category": deal.service_category,
                "pricing_tier": deal.pricing_tier,
                # "budget" ở đây là ô "Giá trị dự kiến" — FREELANCER tự nhập, không phải
                # khách báo. Prompt được dặn dùng đúng con số này làm giá chào.
                "budget": budget,
                # Lời khách — tách riêng để AI không nhầm với thông tin freelancer tự nhập.
                "client_inquiry": getattr(intake, "inquiry_text", None) if intake else None,
                "client_budget": getattr(intake, "estimated_budget", None) if intake else None,
                "client_timeline": (getattr(intake, "desired_timeline", None) if intake else None)
                or deal.desired_timeline,
            },
            client_data={
                "name": client.name if client else "",
                "company_name": company_name,
                "email": client.email if client else "",
            },
            user_profile={
                "name": user.full_name if user else "",
                "email": user.email if user else "",
            },
            template=None,
            user_can_use_ai=user_can_use_ai,
        )

        await AiUsageService(db=self.db).record_cost(
            user_id,
            ai_module="proposal_generator",
            usage=ai_facade.last_usage("proposal_generator"),
        )

        content = await self._apply_pricing(
            content,
            deal,
            user_id,
            (getattr(intake, "estimated_budget", None) if intake else None),
        )

        version_number = await self.repo.count_by_deal(deal_id) + 1
        return await self.repo.create(
            deal_id=deal_id,
            owner_user_id=user_id,
            version_number=version_number,
            status="draft",
            content=content,
            ai_generated=True,
        )

    async def _build_document(self, user_id: uuid.UUID, proposal_id: uuid.UUID):
        """Dựng ProposalDocument cho một báo giá — DÙNG CHUNG cho PDF và cho HTML preview.

        Tách riêng để PDF (tải về) và preview (xem trên màn hình) render từ ĐÚNG MỘT
        document. Nếu hai bên tự dựng lấy thì kiểu gì cũng có ngày lệch — mà bản trên màn
        hình khác bản khách nhận là thứ khiến hệ thống nhìn như lừa đảo.  #Huynh
        """
        proposal = await self._get_proposal(user_id, proposal_id)

        deal = await self.repo.get_deal(proposal.deal_id)
        if deal is None:
            raise NotFoundError(f"Deal {proposal.deal_id} not found")

        client = await self.repo.get_client(deal.client_id) if deal.client_id else None
        user = await self.repo.get_user(user_id)

        company_name = None
        if client and getattr(client, "type", None) == "company":
            company_name = client.name

        # NGÀY PHẢI ĐỨNG YÊN — neo vào sự thật đã lưu, không phải vào "hôm nay".
        #
        # Bản trước lấy `date.today()` cho CẢ HAI ngày, tính lại mỗi lần render. Hậu quả: báo
        # giá lập 17/07 ghi "hiệu lực đến 24/07"; mở đúng nó ngày 30/07 thì thành "lập 30/07,
        # hiệu lực đến 06/08". Hạn tự trườn tới mỗi ngày một ngày, tức là KHÔNG BAO GIỜ hết
        # hạn — và tờ giấy còn khai lại cả ngày sinh của chính nó. Ngay trên đầu hàm có
        # comment tôi tự viết "báo giá không hạn là giá bị treo vô thời hạn", rồi tôi cài
        # đúng cái nó cảnh báo, chỉ khác là có in một con số lên cho giống thật. Thế còn tệ
        # hơn không in gì: nó tạo cảm giác an toàn giả.
        #
        # Đồng hồ chạy từ lúc KHÁCH NHẬN được (`sent_at`), chưa gửi thì tạm tính từ ngày tạo.
        # Freelancer soạn nháp để đó một tuần rồi mới gửi thì không có lý gì hạn đã trôi mất
        # một tuần trước khi khách kịp đọc.  #Huynh
        started = proposal.sent_at or proposal.created_at
        issued_on = (started or datetime.now(UTC)).date()

        # Freelancer tự đặt hạn thì lấy đúng thứ họ đặt. `content` là JSONB tự do nên thêm
        # khoá không đụng gì tới hợp đồng API — cùng lối với `pricing_detail`.
        chosen = _parse_iso_date((proposal.content or {}).get("valid_until"))
        valid_until = chosen or issued_on + timedelta(days=DEFAULT_VALID_DAYS)

        return build_proposal_document(
            proposal.content,
            freelancer_name=user.full_name if user else "",
            freelancer_email=(user.email if user else "") or "",
            freelancer_phone=(getattr(user, "phone", "") if user else "") or "",
            client_name=client.name if client else "",
            client_email=(getattr(client, "email", "") if client else "") or "",
            client_phone=(getattr(client, "phone", "") if client else "") or "",
            company_name=company_name,
            project_type=deal.project_type or deal.title or "",
            proposal_date=_vn_date(issued_on),
            valid_until=_vn_date(valid_until),
        )

    async def render_preview_html(self, user_id: uuid.UUID, proposal_id: uuid.UUID) -> str:
        """HTML xem trước — CHÍNH XÁC những gì PDF sẽ in ra. Frontend nhúng vào card."""
        document = await self._build_document(user_id, proposal_id)
        return ProposalPdfRenderer().render_html(document)

    async def generate_pdf(
        self,
        user_id: uuid.UUID,
        proposal_id: uuid.UUID,
    ) -> bytes:
        document = await self._build_document(user_id, proposal_id)
        return ProposalPdfRenderer().render_pdf(document)

    async def transition_status(
        self, user_id: uuid.UUID, proposal_id: uuid.UUID, target_status: str
    ):  # type: ignore[return]
        proposal = await self._get_proposal(user_id, proposal_id)
        current = proposal.status
        allowed = _VALID_TRANSITIONS.get(current, frozenset())
        if target_status not in allowed:
            raise InvalidStateTransitionError("proposal", current, target_status)

        now = datetime.now(UTC)

        if target_status == "sent":
            # KHÔNG cho gửi khi chưa có GIÁ CỤ THỂ.
            #
            # Một báo giá gửi cho khách phải có một con số. Giá cụ thể đến từ MỘT trong hai:
            #   - `pricing_detail.final_price` (đã chốt từ thanh kéo hoặc gõ tay), HOẶC
            #   - `pricing.total` (báo giá tự soạn đã có sẵn tổng).
            #
            # Nếu chỉ có KHOẢNG (bộ định giá trả về "87–162 triệu" mà chưa chốt) hoặc CHƯA
            # CÓ GÌ (deal chưa chấm điểm nên `pricing` chỉ là câu "Chưa đủ dữ liệu...") thì
            # chặn. Gửi nguyên cái khoảng cho khách là tự bắn vào chân — khách chỉ nhìn con
            # số nhỏ nhất; còn gửi báo giá 0 đồng thì khỏi nói.
            #
            # Bản trước chỉ chặn khi CÓ `pricing_detail` mà thiếu `final_price` — báo giá
            # KHÔNG có `pricing_detail` (deal chưa chấm điểm) lọt lưới, gửi mà chẳng có giá
            # nào. Giờ chặn theo GIÁ CỤ THỂ, không theo sự tồn tại của khối định giá.  #Huynh
            content = proposal.content or {}
            detail = content.get("pricing_detail")
            final_price = detail.get("final_price") if isinstance(detail, dict) else None
            pricing = content.get("pricing")
            dto_total = pricing.get("total") if isinstance(pricing, dict) else None

            has_price = (final_price or 0) > 0 or (dto_total or 0) > 0
            if not has_price:
                raise BusinessRuleError(
                    "Chưa chốt giá. Hãy chọn mức giá bạn muốn chào trước khi gửi cho khách."
                )

            existing = await self.repo.get_sent_by_deal(proposal.deal_id, proposal_id)
            if existing is not None:
                existing.status = "superseded"
            proposal.sent_at = now

        if target_status in ("accepted", "rejected", "expired"):
            proposal.responded_at = now

        proposal.status = target_status
        await self.repo.save(proposal)

        if target_status == "accepted":
            await event_bus.publish(
                "proposals.proposal_accepted",
                {
                    "proposal_id": str(proposal_id),
                    "deal_id": str(proposal.deal_id),
                    "owner_user_id": str(user_id),
                },
            )
        elif target_status == "sent":
            await event_bus.publish(
                "proposals.proposal_sent",
                {
                    "proposal_id": str(proposal_id),
                    "deal_id": str(proposal.deal_id),
                    "owner_user_id": str(user_id),
                },
            )

        return proposal


def _to_decimal(value) -> Decimal | None:  # type: ignore[no-untyped-def]
    """int/Decimal/None -> Decimal|None. Bỏ số 0 và số âm."""
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except (ArithmeticError, ValueError):
        return None
    return number if number > 0 else None


def _parse_money(text: str | None) -> Decimal | None:
    """Boc so tien ra khoi cau khach viet: "45 trieu", "120tr", "50.000.000 VND", "2 ty".

    Khach go tay nen du kieu. Luat doc dau cham/phay:

    - CO tu don vi ("trieu", "ty") -> dau cham la DAU THAP PHAN: "1.5 trieu" = 1.500.000
    - KHONG co tu don vi           -> dau cham la DAU NGAN CACH: "50.000.000" = 50 trieu

    Doc khong chac thi tra None va KHONG canh bao gi. Tha im lang con hon canh bao sai
    ("gia cao hon ngan sach khach 3000%" chi vi doc nham "45 trieu" thanh 45 dong).  #Huynh
    """
    if not text:
        return None

    lowered = text.lower()

    multiplier = Decimal(1)
    if any(unit in lowered for unit in ("ty", "ti", "tỷ", "tỉ")):
        multiplier = Decimal(1_000_000_000)
    elif any(unit in lowered for unit in ("triệu", "tr", "củ")):
        multiplier = Decimal(1_000_000)
    elif any(unit in lowered for unit in ("nghìn", "ngàn", "k")):
        multiplier = Decimal(1_000)

    match = re.search(r"[0-9][0-9.,]*", lowered)
    if not match:
        return None

    raw = match.group().rstrip(".,")
    if multiplier > 1:
        # Co don vi -> cham/phay la dau thap phan. "1,5 trieu" va "1.5 trieu" deu la 1.5.
        raw = raw.replace(",", ".")
        if raw.count(".") > 1:
            return None
    else:
        # Khong don vi -> cham/phay la dau ngan cach nghin. Bo het.
        raw = raw.replace(".", "").replace(",", "")

    try:
        number = Decimal(raw) * multiplier
    except ArithmeticError:
        return None

    return number if number > 0 else None
