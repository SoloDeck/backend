"""Soạn tin nhắn nhắc khách bằng AI (POST /ai/followups/generate)."""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import (
    ClientModel,
    ContractModel,
    DealModel,
    InvoiceModel,
    PlanModel,
    SubscriptionModel,
)
from src.modules.subscriptions.application.ai_usage import AiUsageService
from src.shared.exceptions.domain import NotFoundError, ValidationError

# openapi.yaml khai ReminderTargetType = [deal, client, invoice, contract].
_TARGET_TYPES = frozenset({"deal", "client", "invoice", "contract"})


@dataclass
class FollowUpService:
    """Dựng ngữ cảnh THẬT từ database rồi mới nhờ AI viết.

    Bài học rút ra từ báo giá: nếu để AI viết mà không đưa dữ liệu thật, nó sẽ bịa —
    và tin nhắn này GỬI THẲNG CHO KHÁCH, nên bịa một con số là hứa bậy thay freelancer.
    Vì vậy service tra đúng deal/hoá đơn/hợp đồng ra trước, prompt thì cấm bịa.  #Huynh
    """

    db: AsyncSession

    async def generate(
        self,
        user_id: uuid.UUID,
        *,
        reminder_type: str,
        target_type: str,
        target_id: uuid.UUID,
        ai_facade: Any,
    ) -> dict[str, Any]:
        if target_type not in _TARGET_TYPES:
            raise ValidationError(
                f"target_type must be one of {sorted(_TARGET_TYPES)}, got '{target_type}'"
            )

        # Cổng AI: kiểm tra gói (402), kiểm tra hạn mức tháng (429), ghi nhận lượt dùng.
        # Xem src/modules/subscriptions/application/ai_usage.py  #Huynh
        await AiUsageService(db=self.db).consume(user_id)

        deal_data, client = await self._load_context(user_id, target_type, target_id)

        client_data = {
            "name": client.name if client else "",
            "email": client.email if client else "",
            "phone": client.phone if client else "",
        }

        # Không có gói AI → facade ném EntitlementError → handler trả 402, đúng như
        # openapi.yaml khai cho endpoint này.
        content = await ai_facade.generate_followup(
            deal_data=deal_data,
            client_data=client_data,
            communication_history=[],
            reminder_type=reminder_type,
            user_can_use_ai=await self._can_use_ai(user_id),
        )

        await AiUsageService(db=self.db).record_cost(
            user_id,
            ai_module="followup_generator",
            usage=ai_facade.last_usage("followup_generator"),
        )

        return {
            "message_text": content.get("message_text", ""),
            "subject": content.get("subject", ""),
            "generation_id": str(uuid.uuid4()),
        }

    async def _can_use_ai(self, user_id: uuid.UUID) -> bool:
        sub = await self.db.scalar(
            select(SubscriptionModel).where(SubscriptionModel.user_id == user_id)
        )
        if sub is None:
            return False
        plan = await self.db.scalar(select(PlanModel).where(PlanModel.id == sub.plan_id))
        return bool(plan and plan.can_use_ai)

    async def _load_context(
        self, user_id: uuid.UUID, target_type: str, target_id: uuid.UUID
    ) -> tuple[dict[str, Any], Any]:
        """Trả về (bối cảnh cho AI, khách hàng).

        CHỈ đưa vào những trường có thật. Thiếu thì để trống — prompt được dặn thà nhắc
        mơ hồ còn hơn nhắc sai một con số rồi khách tin theo.
        """
        if target_type == "deal":
            deal = await self._get_owned(DealModel, target_id, user_id)
            client = await self._get_client(deal.client_id, user_id)
            return {
                "loại": "deal",
                "tên dự án": deal.title,
                "giai đoạn": deal.stage,
                "giá trị dự kiến": self._money(deal.estimated_value, deal.currency),
                "ghi chú": deal.notes,
            }, client

        if target_type == "client":
            client = await self._get_owned(ClientModel, target_id, user_id)
            return {"loại": "client", "tên khách": client.name}, client

        if target_type == "invoice":
            invoice = await self._get_owned(InvoiceModel, target_id, user_id)
            client = await self._get_client(invoice.client_id, user_id)
            # Cột là `total` và `amount_paid` — tôi viết nhầm `total_amount` nên endpoint
            # ném AttributeError → 500. Bài học: đọc model trước, đừng đoán tên cột.  #Huynh
            remaining = (invoice.total or 0) - (invoice.amount_paid or 0)
            return {
                "loại": "hoá đơn",
                "số hoá đơn": invoice.invoice_number,
                "tổng tiền": self._money(invoice.total, invoice.currency),
                "đã thanh toán": self._money(invoice.amount_paid, invoice.currency),
                "còn phải trả": self._money(remaining, invoice.currency),
                "hạn thanh toán": str(invoice.due_date) if invoice.due_date else None,
                "trạng thái": invoice.status,
            }, client

        contract = await self._get_owned(ContractModel, target_id, user_id)
        client = await self._get_client(contract.client_id, user_id)
        return {
            "loại": "hợp đồng",
            "trạng thái": contract.status,
            "phiên bản": contract.version_number,
        }, client

    async def _get_owned(self, model: Any, target_id: uuid.UUID, user_id: uuid.UUID) -> Any:
        row = await self.db.scalar(
            select(model).where(model.id == target_id, model.owner_user_id == user_id)
        )
        if row is None:
            raise NotFoundError(f"{model.__name__} {target_id} not found")
        return row

    async def _get_client(self, client_id: uuid.UUID | None, user_id: uuid.UUID) -> Any:
        if client_id is None:
            return None
        return await self.db.scalar(
            select(ClientModel).where(
                ClientModel.id == client_id, ClientModel.owner_user_id == user_id
            )
        )

    @staticmethod
    def _money(amount: Any, currency: str | None) -> str | None:
        """Định dạng tiền TRƯỚC khi đưa cho AI.

        Đưa vào "700000 VND" thì AI chép nguyên xi vào tin nhắn gửi khách — trông cẩu
        thả. Định dạng sẵn ở đây để nó chỉ việc dùng lại: "700.000 ₫".  #Huynh
        """
        if amount is None:
            return None
        try:
            number = float(amount)
        except (TypeError, ValueError):
            return f"{amount} {currency or 'VND'}"

        formatted = f"{number:,.0f}".replace(",", ".")
        return f"{formatted} ₫" if (currency or "VND") == "VND" else f"{formatted} {currency}"
