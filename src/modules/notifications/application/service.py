"""Nghiệp vụ thông báo trong ứng dụng.

Ngoài CRUD, file này giữ **danh mục loại thông báo** và cách viết câu chữ cho từng loại.
Gom vào một chỗ để mọi thông báo nói cùng một giọng, và để sau này dịch/đổi câu chữ chỉ
phải sửa một nơi.  #Huynh
"""

import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import NotificationModel
from src.modules.notifications.infrastructure.repository import NotificationRepository

log = structlog.get_logger(__name__)

# Loại thông báo. Dùng hằng số thay vì gõ chuỗi rải rác — gõ sai "intake_submited" thì
# không ai phát hiện cho tới khi lọc theo loại và thấy trống trơn.
TYPE_INTAKE_SUBMITTED = "intake_submitted"
TYPE_DEAL_QUALIFIED = "deal_qualified"
TYPE_INVOICE_OVERDUE = "invoice_overdue"
TYPE_REMINDER_DUE = "reminder_due"
TYPE_REMINDER_SENT = "reminder_sent"
TYPE_REMINDER_FAILED = "reminder_failed"


@dataclass
class NotificationService:
    db: AsyncSession

    def __post_init__(self) -> None:
        self.repo = NotificationRepository(self.db)

    async def notify(
        self,
        *,
        user_id: uuid.UUID,
        type: str,
        title: str,
        body: str | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
    ) -> NotificationModel:
        return await self.repo.create(
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            entity_type=entity_type,
            entity_id=entity_id,
        )

    # --- Các loại thông báo cụ thể -------------------------------------------------

    async def notify_intake_submitted(
        self,
        *,
        owner_user_id: uuid.UUID,
        deal_id: uuid.UUID,
        client_name: str,
        project_name: str | None,
    ) -> NotificationModel:
        """Khách vừa gửi Biểu mẫu tiếp nhận → có deal mới trong cột "Deal Mới"."""
        project = project_name or "một yêu cầu mới"
        return await self.notify(
            user_id=owner_user_id,
            type=TYPE_INTAKE_SUBMITTED,
            title="Khách hàng mới gửi yêu cầu",
            body=f"{client_name} vừa gửi yêu cầu “{project}” qua biểu mẫu tiếp nhận.",
            entity_type="deal",
            entity_id=deal_id,
        )

    async def notify_deal_qualified(
        self,
        *,
        owner_user_id: uuid.UUID,
        deal_id: uuid.UUID,
        deal_title: str,
        score: int,
        level: str,
    ) -> NotificationModel:
        """AI chấm điểm xong (chạy nền, nên người dùng không đứng đợi trước màn hình)."""
        # Giữ nguyên HOT/WARM/COLD theo yêu cầu của Phiếu đề tài — KHÔNG dịch sang tiếng
        # Việt. Đây là thuật ngữ nghiệp vụ, và cũng là giá trị hệ thống dùng, nên thông báo,
        # màn hình và tài liệu đề tài nói cùng một ngôn ngữ.  #Huynh
        return await self.notify(
            user_id=owner_user_id,
            type=TYPE_DEAL_QUALIFIED,
            title=f"AI đã chấm điểm: {score}/100 — {level.upper()}",
            body=f"Deal “{deal_title}” đã được chấm điểm. Bấm để xem căn cứ chấm điểm.",
            entity_type="deal",
            entity_id=deal_id,
        )

    async def notify_invoice_overdue(
        self,
        *,
        owner_user_id: uuid.UUID,
        invoice_id: uuid.UUID,
        invoice_number: str,
        client_name: str,
        days_overdue: int,
    ) -> NotificationModel:
        return await self.notify(
            user_id=owner_user_id,
            type=TYPE_INVOICE_OVERDUE,
            title=f"Hoá đơn {invoice_number} đã quá hạn {days_overdue} ngày",
            body=f"Khách {client_name} chưa thanh toán. Cân nhắc gửi lời nhắc.",
            entity_type="invoice",
            entity_id=invoice_id,
        )

    async def notify_reminder_due(
        self,
        *,
        owner_user_id: uuid.UUID,
        reminder_id: uuid.UUID,
        client_name: str | None,
        message_preview: str | None,
    ) -> NotificationModel:
        """Lời nhắc kênh "trong ứng dụng" tới giờ — reo cho chính freelancer."""
        who = f" khách {client_name}" if client_name else ""
        return await self.notify(
            user_id=owner_user_id,
            type=TYPE_REMINDER_DUE,
            title=f"Đến giờ nhắc{who}",
            body=(message_preview or "").strip() or "Bạn có một lời nhắc đến hạn.",
            entity_type="reminder",
            entity_id=reminder_id,
        )

    async def notify_reminder_sent(
        self,
        *,
        owner_user_id: uuid.UUID,
        reminder_id: uuid.UUID,
        client_name: str | None,
        recipient: str,
    ) -> NotificationModel:
        """Hệ thống vừa gửi email cho khách THAY MẶT freelancer.

        Đây là biên nhận, không phải lời nhắc. Hệ thống vừa thay mặt người dùng liên hệ
        khách hàng của họ trong lúc họ không ngồi trước máy — họ phải được biết chuyện đó
        đã xảy ra, gửi cho ai, và biết mà chờ khách trả lời.  #Huynh
        """
        who = client_name or "khách hàng"
        return await self.notify(
            user_id=owner_user_id,
            type=TYPE_REMINDER_SENT,
            title=f"Đã gửi email nhắc {who}",
            body=f"SoloDesk vừa gửi email tới {recipient} thay bạn. Khách trả lời sẽ về hộp thư của bạn.",
            entity_type="reminder",
            entity_id=reminder_id,
        )

    async def notify_reminder_failed(
        self,
        *,
        owner_user_id: uuid.UUID,
        reminder_id: uuid.UUID,
        client_name: str | None,
        reason: str,
    ) -> NotificationModel:
        """Không gửi được lời nhắc.

        Luôn kèm LÝ DO. Chỉ báo "gửi lỗi" thì người dùng không biết phải sửa gì — mà
        phần lớn nguyên nhân đều tự sửa được (khách chưa có email, chưa nối Zalo).  #Huynh
        """
        who = f" cho {client_name}" if client_name else ""
        return await self.notify(
            user_id=owner_user_id,
            type=TYPE_REMINDER_FAILED,
            title=f"Chưa gửi được lời nhắc{who}",
            body=reason,
            entity_type="reminder",
            entity_id=reminder_id,
        )

    # --- Đọc -----------------------------------------------------------------------

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        unread_only: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[NotificationModel], int]:
        return await self.repo.list_for_user(
            user_id, unread_only=unread_only, page=page, page_size=page_size
        )

    async def count_unread(self, user_id: uuid.UUID) -> int:
        return await self.repo.count_unread(user_id)

    async def mark_read(self, user_id: uuid.UUID, notification_id: uuid.UUID) -> bool:
        return await self.repo.mark_read(user_id, notification_id)

    async def mark_all_read(self, user_id: uuid.UUID) -> int:
        return await self.repo.mark_all_read(user_id)
