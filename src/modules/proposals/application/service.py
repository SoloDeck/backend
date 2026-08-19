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
from src.ai.proposal_generator.schemas.proposal_document import (
    PaymentMilestone,
    default_payment_milestones,
)
from src.modules.deals.infrastructure.repository import DealsRepository
from src.modules.proposals.application.pdf_content import (
    DUE_CUSTOM,
    CostItem,
    build_proposal_document,
    extract_payment_milestones,
    infer_due_type,
    resolve_cost_items,
)
from src.modules.proposals.infrastructure.repository import ProposalsRepository
from src.modules.proposals.schemas.request import ProposalRequest
from src.modules.subscriptions.application.ai_usage import AiUsageService
from src.modules.tasks.application.service import PAYMENT_TASK_PREFIX, BillingTaskPayload
from src.shared.domain.template_blocks import (
    VALID_DAYS_KEY,
    apply_template_blocks,
    build_skeleton_content,
)
from src.shared.events.bus import event_bus
from src.shared.exceptions.domain import (
    BusinessRuleError,
    InvalidStateTransitionError,
    NotFoundError,
    ValidationError,
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


def _cost_items_to_payloads(items: list[CostItem]) -> list[BillingTaskPayload]:
    """Hạng mục chi phí (mục 7) → task THU TIỀN, một đổi một.

    Tên task là NHÃN HẠNG MỤC nguyên văn — đây vừa là việc phải làm vừa là đợt thu tiền, nên
    freelancer đọc bảng việc thấy đúng công việc thật chứ không phải "Thu tiền: Đặt cọc khi ký
    hợp đồng". Số tiền vào cột `billing_amount`, không nhét vào tên: sửa tên không được phép
    làm đứt đường xuất hoá đơn nữa.  #Huynh
    """
    payloads: list[BillingTaskPayload] = []
    for item in items:
        desc_parts = [
            f"Số tiền: {item.amount:,.0f} đ".replace(",", "."),
            f"Thời điểm thu: {item.due_label}",
        ]
        payloads.append(
            BillingTaskPayload(
                title=item.label[:500],
                amount=Decimal(item.amount),
                description="\n".join(desc_parts),
                due_type=item.due_type,
            )
        )
    return payloads


def _milestones_to_payloads(
    milestones: list[PaymentMilestone], total: Decimal
) -> list[BillingTaskPayload]:
    """Mốc thanh toán theo % → task thu tiền. LỐI RƠI VỀ cho báo giá cũ không có hạng mục nào.

    Giữ tiền tố `PAYMENT_TASK_PREFIX` trong tên để nhìn vào bảng việc là biết ngay đây là deal
    theo lịch cũ. Tiền vẫn ghi vào `billing_amount` như mọi task thu tiền khác — chỉ khác chỗ
    con số tới từ đâu.  #Huynh"""
    percents = [m.percent for m in milestones]
    known = sum(p for p in percents if p is not None)
    missing = [i for i, p in enumerate(percents) if p is None]
    share = (
        (max(Decimal(0), Decimal(100) - Decimal(known)) / len(missing))
        if missing
        else Decimal(0)
    )

    amounts: list[Decimal] = [
        (total * (Decimal(p) if p is not None else share) / Decimal(100)).quantize(Decimal("1"))
        for p in percents
    ]
    # Đồng lẻ dồn vào mốc CUỐI để tổng khớp tuyệt đối giá chốt — cùng quy tắc với bảng chi phí.
    if amounts and Decimal(known) + share * len(missing) == 100:
        amounts[-1] += total - sum(amounts)

    payloads: list[BillingTaskPayload] = []
    for m, amount in zip(milestones, amounts, strict=True):
        desc_parts = [f"Số tiền: {amount:,.0f} đ".replace(",", ".")]
        if m.due:
            desc_parts.append(f"Thời điểm/điều kiện: {m.due}")
        payloads.append(
            BillingTaskPayload(
                title=f"{PAYMENT_TASK_PREFIX} {m.label}"[:500],
                amount=amount,
                description="\n".join(desc_parts),
                # Mốc cũ chỉ có chữ tự do nên phải suy. Suy không ra thì để `None` — bảng việc
                # im lặng, thà thiếu một nhãn còn hơn nhắc sai.  #Huynh
                due_type=infer_due_type(f"{m.label} {m.due}"),
            )
        )
    return payloads


async def billing_task_payloads_for_deal(
    db: AsyncSession, deal_id: uuid.UUID, owner_user_id: uuid.UUID
) -> list[BillingTaskPayload]:
    """Payloads task THU TIỀN lấy từ báo giá ĐÃ CHỐT của deal (rỗng nếu chưa chốt báo giá nào).

    Contracts gọi hàm này khi hợp đồng được ghi nhận đã ký; deals gọi lại khi vào `active` để
    vá dữ liệu cũ. Đặt ở proposals vì hạng mục chi phí là chuyện của báo giá.

    Nguồn là `resolve_cost_items` — ĐÚNG hàm mà tờ báo giá dùng để in bảng mục 7, nên số task
    và số tiền không thể lệch khỏi thứ khách cầm trên tay. Lưu ý: KHÔNG đọc thẳng
    `content["pricing_items"]`. Khoá đó thường KHÔNG có trong DB (chỉ frontend ghi, và nó vừa
    được sửa lỗi làm rụng) — đọc thẳng là hầu hết deal ra 0 task, guard đóng dự án pass vô điều
    kiện và bảng doanh thu về 0 đ. `resolve_cost_items` đi hết chuỗi tới bảng của bộ định giá.

    Báo giá cũ không có hạng mục nào thì rơi về mốc % (hoặc lịch chuẩn 50/50) — vẫn phải có
    task thu tiền cho freelancer theo dõi, thay vì để trống.  #Huynh"""
    proposal = await ProposalsRepository(db).get_accepted_by_deal(deal_id, owner_user_id)
    if proposal is None:
        return []

    content = proposal.content or {}
    items = resolve_cost_items(content)
    if items:
        return _cost_items_to_payloads(items)

    deal = await DealsRepository(db).get_by_id(deal_id, owner_user_id)
    total = Decimal(getattr(deal, "estimated_value", None) or 0)
    milestones = extract_payment_milestones(content) or default_payment_milestones()
    return _milestones_to_payloads(milestones, total)


def _apply_template_valid_days(content: dict, template_content: dict) -> dict:
    """Mẫu gợi ý số ngày hiệu lực báo giá.

    CHỈ áp khi freelancer chưa tự đặt hạn — mẫu là giá trị mặc định, không phải lệnh ghi đè
    lên thứ người dùng đã gõ. Khác hẳn các khối văn bản (mẫu thắng AI), vì đây là thứ CON
    NGƯỜI đặt chứ không phải AI sinh.  #Huynh
    """
    if not isinstance(template_content, dict):
        return content
    if str(content.get("valid_until") or "").strip():
        return content

    raw = template_content.get(VALID_DAYS_KEY)
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return content
    if days <= 0:
        return content

    out = dict(content)
    out["valid_until"] = (datetime.now(UTC).date() + timedelta(days=days)).isoformat()
    return out


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

    async def generate_content(  # type: ignore[no-untyped-def]
        self,
        user_id: uuid.UUID,
        proposal_id: uuid.UUID,
        ai_facade,
        *,
        template_id: uuid.UUID | None = None,
    ):
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
        content = await self._apply_chosen_template(content, template_id, user)

        proposal.content = content
        proposal.ai_generated = True
        return await self.repo.save(proposal)

    async def list_term_templates(self, user_id: uuid.UUID) -> list:
        """Mẫu điều khoản báo giá freelancer được chọn (theo nghề của họ + dùng chung)."""
        user = await self.repo.get_user(user_id)
        profession = getattr(user, "profession", None) if user else None
        return await self.repo.list_active_templates(
            template_type="proposal", profession=profession
        )

    async def _apply_chosen_template(  # type: ignore[no-untyped-def]
        self, content: dict, template_id: uuid.UUID | None, user
    ) -> dict:
        """Chèn điều khoản từ mẫu freelancer CHỌN, NGUYÊN VĂN. AI lo phần thân báo giá;
        điều khoản chuẩn giữ đúng chữ admin. Không chọn ("AI tự viết") thì để nguyên.  #Huynh
        """
        if template_id is None:
            return content
        profession = getattr(user, "profession", None) if user else None
        template = await self.repo.get_template_for_use(
            template_id, template_type="proposal", profession=profession
        )
        if template is None:
            raise ValidationError("Mẫu điều khoản không hợp lệ hoặc không dùng được.")
        content = apply_template_blocks(content, template.content, "proposal")
        return _apply_template_valid_days(content, template.content)

    async def create_from_template(  # type: ignore[no-untyped-def]
        self,
        user_id: uuid.UUID,
        deal_id: uuid.UUID,
        *,
        template_id: uuid.UUID | None = None,
    ):
        """Tạo bản nháp báo giá từ KHUNG mẫu — KHÔNG gọi AI, KHÔNG tốn lượt.

        Đường soạn thứ hai, dành cho freelancer không muốn nhờ AI (và cho gói Free vốn bị chặn
        402 ở mọi endpoint AI). Trước đây thư viện mẫu chỉ với được từ trong bụng hai hàm
        `generate_*`, tức là muốn dùng mẫu thì bắt buộc phải tiêu một lượt AI — dù
        `build_skeleton_content` không cần LLM một chút nào.

        CỐ Ý không gọi `_apply_pricing`: bộ định giá đọc `complexity`/`scale`/`line_item_weights`
        do AI vừa sinh, không có AI thì không có mấy trường đó. Freelancer tự chốt giá qua
        `PATCH /proposals/{id}/price`, và cổng gửi chỉ đòi một con số > 0 nên đường này đi lọt
        mà không phải nới cổng nào.

        `template_id = None` là hợp lệ: "khung trắng", tờ giấy trống với đủ ô để tự điền.  #Huynh
        """
        deal = await self.repo.get_deal(deal_id)
        if deal is None or deal.owner_user_id != user_id:
            raise NotFoundError(f"Deal {deal_id} not found")

        content: dict = {}
        if template_id is not None:
            user = await self.repo.get_user(user_id)
            profession = getattr(user, "profession", None) if user else None
            template = await self.repo.get_template_for_use(
                template_id, template_type="proposal", profession=profession
            )
            if template is None:
                raise ValidationError("Mẫu điều khoản không hợp lệ hoặc không dùng được.")
            content = build_skeleton_content(template.content, "proposal")
            content = _apply_template_valid_days(content, template.content)

        version_number = await self.repo.count_by_deal(deal_id) + 1
        return await self.repo.create(
            deal_id=deal_id,
            owner_user_id=user_id,
            version_number=version_number,
            status="draft",
            content=content,
            ai_generated=False,
        )

    async def generate_from_deal(  # type: ignore[no-untyped-def]
        self,
        user_id: uuid.UUID,
        deal_id: uuid.UUID,
        ai_facade,
        *,
        template_id: uuid.UUID | None = None,
    ):
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
        content = await self._apply_chosen_template(content, template_id, user)

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

    async def render_preview_html(
        self, user_id: uuid.UUID, proposal_id: uuid.UUID, *, editable: bool = False
    ) -> str:
        """HTML xem trước — CHÍNH XÁC những gì PDF sẽ in ra. Frontend nhúng vào card.

        `editable=True` chỉ dùng cho bản nháp đang soạn: thêm ô rỗng cho các mục chưa có chữ để
        freelancer bấm vào nhập. Mặc định tắt, nên mọi đường khác vẫn ra đúng bản khách nhận.
        """
        document = await self._build_document(user_id, proposal_id)
        return ProposalPdfRenderer().render_html(document, editable=editable)

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

            # --- CỔNG TIỀN -------------------------------------------------------------
            #
            # Từ khi thu tiền theo hạng mục, hạng mục chi phí là ĐƠN VỊ THU TIỀN: mỗi dòng ở
            # mục 7 thành một task và một hoá đơn. Nên cổng gửi phải soi đúng nó.
            #
            # Cổng "tổng mốc thanh toán = 100%" của bản cũ đã BỎ: mục 8 giờ suy ra từ mục 7
            # (`pdf_content.payment_schedule`) chứ không ai gõ tay nữa, nên không còn cách nào
            # cộng ra 130%. Giữ lại là chặn oan chính dữ liệu mình vừa sinh.
            #
            # Dùng ĐÚNG `resolve_cost_items` mà bảng PDF và bộ sinh task dùng — ba nơi không
            # bao giờ hiểu khác nhau về "hạng mục chi phí là gì".  #Huynh
            cost_items = resolve_cost_items(content)
            agreed = int(final_price or dto_total or 0)

            # KHÔNG có hạng mục nào: cổng dưới viết `if cost_items and agreed > 0` nên báo giá
            # trắng hạng mục ĐI LỌT toàn bộ khối kiểm này.
            #
            # Lọt rồi thì cuối đường `resolve_cost_items` trả rỗng, bộ sinh task rơi xuống nhánh
            # chia mốc % nhân `deal.estimated_value` và đẻ ra HAI task chung chung ("đặt cọc 50%
            # / bàn giao 50%") — trái hẳn quy tắc mỗi hạng mục là một đợt thu tiền và một hoá
            # đơn, mà freelancer không hề được báo là mình vừa nhận kiểu task khác.
            #
            # Đường KHUNG (không AI) rơi vào đây mặc định: mẫu tuyệt đối không mang tiền nên
            # bảng mục 7 mở ra trống trơn. Đường AI thường không dính vì bảng đã dựng sẵn từ
            # `pricing_detail.line_items` — trừ khi AI không trả tỉ trọng công sức, và khi đó
            # chặn cũng đúng chứ không oan.  #Huynh
            if not cost_items:
                raise BusinessRuleError(
                    "Chưa có hạng mục chi phí nào. Mỗi hạng mục ở mục 'Hạng mục chi phí' là một "
                    "đợt thu tiền — hệ thống dựa vào đó để tạo task và hoá đơn sau khi ký hợp "
                    "đồng. Hãy thêm ít nhất một hạng mục trước khi gửi."
                )

            # Hạng mục 0 đồng: lọt qua được vì cổng dưới chỉ kiểm TỔNG. Hậu quả là một task
            # thu tiền 0 đồng — bắt buộc tick xong mới đóng được dự án, nhưng bấm xuất hoá đơn
            # thì bị từ chối ("Mốc này đang là 0 đồng"). Deal kẹt vĩnh viễn, không lối ra.
            zero_items = [item.label for item in cost_items if item.amount <= 0]
            if zero_items:
                raise BusinessRuleError(
                    f"Hạng mục '{zero_items[0]}' đang là 0 đồng. Mỗi hạng mục là một đợt thu "
                    "tiền, nên phải có số tiền cụ thể. Hãy điền số tiền hoặc xoá hạng mục này."
                )

            # Chọn "Khác" mà bỏ trống ghi chú: tờ giấy khách KÝ sẽ có ô "thời điểm thu" mơ hồ,
            # đúng thứ đẻ ra cãi nhau lúc đòi tiền. Cùng lý do với cổng 0 đồng ngay trên.
            vague = [
                item.label
                for item in cost_items
                if item.due_type == DUE_CUSTOM and not item.due_note.strip()
            ]
            if vague:
                raise BusinessRuleError(
                    f"Hạng mục '{vague[0]}' chọn thời điểm thu 'Khác' nhưng chưa ghi rõ là khi "
                    "nào. Hãy ghi cụ thể hoặc chọn một mốc có sẵn."
                )

            # KHÔNG cho gửi khi tổng các hạng mục ≠ giá chào khách: khách cầm tờ báo giá tự
            # cộng cột "Thành tiền" ra một số, rồi đọc dòng "Tổng báo giá" ra số khác. Mất uy
            # tín ngay tại bàn, và không cãi được.
            # Không cần `if cost_items` nữa — cổng ngay trên đã bảo đảm có ít nhất một hạng mục.
            if agreed > 0:
                items_total = sum(item.amount for item in cost_items)
                if items_total != agreed:
                    raise BusinessRuleError(
                        f"Tổng các hạng mục chi phí đang là {items_total:,.0f} đ, "
                        f"nhưng giá chào khách là {agreed:,.0f} đ. "
                        "Hãy sửa mục 'Hạng mục chi phí' cho khớp trước khi gửi."
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
            # KHÔNG sinh task thanh toán ở đây: chốt báo giá mới chỉ là khách gật đầu, chưa ký
            # gì cả — chưa có gì để đi đòi tiền. Task "Thu tiền:" sinh khi HỢP ĐỒNG được ghi
            # nhận đã ký (`ContractsService.transition_status` -> active), và sinh lại lần nữa
            # khi deal vào active để vá dữ liệu cũ — cả hai đều gọi
            # `payment_task_payloads_for_deal` và đều idempotent. Ở đây chỉ phát sự kiện.  #Huynh
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
