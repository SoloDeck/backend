"""File khách gửi kèm deal — lưu trữ + bóc chữ cho AI."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import DealAttachmentModel, DealModel
from src.infrastructure.storage.object_storage import (
    ALLOWED_CONTENT_TYPES,
    MAX_FILE_SIZE_BYTES,
    object_storage,
    resolve_content_type,
)
from src.modules.deals.application.attachment_text import extract_pdf_text
from src.shared.exceptions.domain import BusinessRuleError, NotFoundError, ValidationError


@dataclass
class DealAttachmentService:
    db: AsyncSession

    async def upload(
        self,
        user_id: uuid.UUID,
        deal_id: uuid.UUID,
        *,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> DealAttachmentModel:
        """Lưu file lên object storage, bóc chữ nếu là PDF."""
        await self._get_owned_deal(user_id, deal_id)

        # Trình duyệt Windows đôi khi trả content_type rỗng cho đúng file PDF. Suy từ đuôi
        # file thay vì từ chối thẳng.  #Huynh
        content_type = resolve_content_type(content_type, filename)

        if content_type not in ALLOWED_CONTENT_TYPES:
            raise ValidationError(
                f"Định dạng '{content_type}' không được hỗ trợ. "
                f"Chỉ nhận PDF, ảnh (PNG/JPEG/WebP), Word và Excel."
            )

        if len(data) > MAX_FILE_SIZE_BYTES:
            raise ValidationError(
                f"File quá lớn ({len(data) / 1024 / 1024:.1f} MB). "
                f"Tối đa {MAX_FILE_SIZE_BYTES // 1024 // 1024} MB."
            )

        if not object_storage.enabled:
            raise BusinessRuleError(
                "Object storage chưa được cấu hình (thiếu STORAGE_ENDPOINT/ACCESS_KEY)."
            )

        storage_key = object_storage.upload(
            data=data,
            content_type=content_type,
            prefix=f"deals/{deal_id}",
            filename=filename,
        )

        # Bóc chữ NGAY lúc upload, lưu sẵn vào DB.
        #
        # Không bóc lại mỗi lần chấm điểm: bóc PDF tốn CPU, mà một deal có thể chấm lại
        # nhiều lần. Bóc một lần, dùng mãi.  #Huynh
        extracted = extract_pdf_text(data) if content_type == "application/pdf" else None

        attachment = DealAttachmentModel(
            id=uuid.uuid4(),
            deal_id=deal_id,
            owner_user_id=user_id,
            filename=filename,
            content_type=content_type,
            size_bytes=len(data),
            storage_key=storage_key,
            extracted_text=extracted,
        )
        self.db.add(attachment)
        await self.db.flush()
        await self.db.refresh(attachment)
        return attachment

    async def list_for_deal(
        self, user_id: uuid.UUID, deal_id: uuid.UUID
    ) -> list[DealAttachmentModel]:
        await self._get_owned_deal(user_id, deal_id)
        rows = await self.db.scalars(
            select(DealAttachmentModel)
            .where(
                DealAttachmentModel.deal_id == deal_id,
                DealAttachmentModel.owner_user_id == user_id,
            )
            .order_by(DealAttachmentModel.created_at.desc())
        )
        return list(rows)

    async def download(
        self, user_id: uuid.UUID, attachment_id: uuid.UUID
    ) -> tuple[bytes, str, str]:
        """Trả về (bytes, content_type, filename)."""
        attachment = await self._get_owned(user_id, attachment_id)
        data, content_type = object_storage.download(attachment.storage_key)
        return data, content_type or attachment.content_type, attachment.filename

    async def delete(self, user_id: uuid.UUID, attachment_id: uuid.UUID) -> None:
        attachment = await self._get_owned(user_id, attachment_id)
        object_storage.delete(attachment.storage_key)
        await self.db.delete(attachment)
        await self.db.flush()

    async def _get_owned(
        self, user_id: uuid.UUID, attachment_id: uuid.UUID
    ) -> DealAttachmentModel:
        attachment = await self.db.scalar(
            select(DealAttachmentModel).where(
                DealAttachmentModel.id == attachment_id,
                DealAttachmentModel.owner_user_id == user_id,
            )
        )
        if attachment is None:
            raise NotFoundError(f"Attachment {attachment_id} not found")
        return attachment

    async def _get_owned_deal(self, user_id: uuid.UUID, deal_id: uuid.UUID) -> DealModel:
        deal = await self.db.scalar(
            select(DealModel).where(
                DealModel.id == deal_id, DealModel.owner_user_id == user_id
            )
        )
        if deal is None:
            raise NotFoundError(f"Deal {deal_id} not found")
        return deal
