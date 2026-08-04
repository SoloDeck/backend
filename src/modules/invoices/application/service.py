"""Invoices application service."""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.invoices.infrastructure.repository import InvoicesRepository
from src.modules.invoices.schemas.request import (
    InvoiceRequest,
    InvoiceUpdateRequest,
    PaymentRequest,
)
from src.shared.exceptions.domain import BusinessRuleError, NotFoundError


@dataclass
class InvoicesService:
    db: AsyncSession
    repo: InvoicesRepository | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = InvoicesRepository(self.db)

    async def _get_invoice(self, user_id: uuid.UUID, invoice_id: uuid.UUID):  # type: ignore[return]
        invoice = await self.repo.get_by_id(invoice_id, user_id)
        if invoice is None:
            raise NotFoundError(f"Invoice {invoice_id} not found")
        return invoice

    async def create(self, user_id: uuid.UUID, payload: InvoiceRequest):  # type: ignore[return]
        if payload.deal_id is None and payload.contract_id is None:
            raise BusinessRuleError("Invoice must be linked to a deal or contract")
        client = await self.repo.get_client_by_id(payload.client_id, user_id)
        if client is None:
            raise NotFoundError(f"Client {payload.client_id} not found")
        if (
            payload.deal_id is not None
            and await self.repo.get_deal_by_id(payload.deal_id, user_id) is None
        ):
            raise NotFoundError(f"Deal {payload.deal_id} not found")
        if (
            payload.contract_id is not None
            and await self.repo.get_contract_by_id(payload.contract_id, user_id) is None
        ):
            raise NotFoundError(f"Contract {payload.contract_id} not found")

        subtotal = payload.subtotal
        if subtotal is None:
            if not payload.line_items:
                raise BusinessRuleError("Invoice requires subtotal or line_items")
            subtotal = sum((i.quantity * i.unit_price for i in payload.line_items), Decimal("0"))
        if subtotal <= 0:
            raise BusinessRuleError("Invoice subtotal must be greater than zero")
        tax_amount = subtotal * payload.tax_rate
        total = subtotal + tax_amount
        invoice_number = (
            f"INV-{datetime.now(UTC).strftime('%Y%m%d')}-{secrets.token_hex(2).upper()}"
        )

        invoice = await self.repo.create(
            owner_user_id=user_id,
            client_id=payload.client_id,
            contract_id=payload.contract_id,
            deal_id=payload.deal_id,
            invoice_number=invoice_number,
            status="draft",
            issue_date=payload.issue_date or date.today(),
            due_date=payload.due_date,
            currency=payload.currency,
            subtotal=subtotal,
            tax_rate=payload.tax_rate,
            tax_amount=tax_amount,
            total=total,
            amount_paid=0,
            notes=payload.notes,
            client_snapshot={},
        )
        for item in payload.line_items or []:
            await self.repo.add_line_item(
                invoice_id=invoice.id,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                amount=item.quantity * item.unit_price,
                sort_order=item.sort_order,
            )
        return await self.repo.save(invoice)

    async def list_all(
        self,
        user_id: uuid.UUID,
        status: str | None = None,
        invoice_number: str | None = None,
    ) -> list:
        return await self.repo.list_all(user_id, status=status, invoice_number=invoice_number)

    async def get_one(self, user_id: uuid.UUID, invoice_id: uuid.UUID):  # type: ignore[return]
        return await self._get_invoice(user_id, invoice_id)

    async def update(self, user_id: uuid.UUID, invoice_id: uuid.UUID, payload: InvoiceUpdateRequest):  # type: ignore[return]
        invoice = await self._get_invoice(user_id, invoice_id)
        if invoice.status != "draft":
            raise BusinessRuleError("Only draft invoices can be updated")
        if payload.line_items:
            payload.subtotal = sum(
                (i.quantity * i.unit_price for i in payload.line_items), Decimal("0")
            )
            await self.repo.replace_line_items(invoice_id, payload.line_items)
        if payload.subtotal is not None:
            invoice.subtotal = payload.subtotal
        if payload.tax_rate is not None:
            invoice.tax_rate = payload.tax_rate
        invoice.tax_amount = invoice.subtotal * invoice.tax_rate
        invoice.total = invoice.subtotal + invoice.tax_amount
        if payload.due_date is not None:
            invoice.due_date = payload.due_date
        if payload.notes is not None:
            invoice.notes = payload.notes
        return await self.repo.save(invoice)

    async def delete(self, user_id: uuid.UUID, invoice_id: uuid.UUID) -> None:
        invoice = await self._get_invoice(user_id, invoice_id)
        await self.repo.delete(invoice)

    async def _build_invoice_email(self, invoice, attachments: list[dict[str, str]] | None):
        """Dựng lá thư gửi khách. Trả `(EmailContent, ảnh_nhúng, email_khách)`.

        Dùng lại nguyên đường ống của lời nhắc thanh toán thay vì dựng bộ thứ hai:
        `payment_info_from_owner` + `build_payment_block` (đã sinh QR VietQR kèm sẵn số tiền
        và nội dung chuyển khoản), và `parse_attachments`/`load_image_bytes` cho ảnh
        freelancer tự đính. Hai bộ dựng thư song song là kiểu gì cũng có ngày lệch nhau, mà
        lệch ở đây nghĩa là khách chuyển tiền nhầm chỗ.  #Huynh
        """
        from src.infrastructure.storage.object_storage import object_storage
        from src.modules.invoices.application.emails import build_invoice_email
        from src.modules.reminders.application.attachments import (
            images_html,
            load_image_bytes,
            parse_attachments,
        )
        from src.modules.reminders.application.delivery_service import build_footer
        from src.modules.reminders.application.payment_block import (
            build_payment_block,
            payment_info_from_owner,
        )

        client = await self.repo.get_client_by_id(invoice.client_id, invoice.owner_user_id)
        owner = await self.repo.get_owner(invoice.owner_user_id)
        items = await self.repo.list_line_items(invoice.id)

        if client is None or not (client.email or "").strip():
            raise BusinessRuleError(
                "Khách hàng của hóa đơn này chưa có email, chưa gửi được. "
                "Bổ sung email cho khách rồi gửi lại."
            )

        amount_due = Decimal(invoice.total or 0) - Decimal(invoice.amount_paid or 0)

        # Ảnh freelancer tự đính. Có ảnh riêng thì KHÔNG kèm QR tự sinh nữa: hai mã QR cạnh
        # nhau là khách phải phân vân quét cái nào, mà đoán sai thì tiền đi nhầm chỗ.
        images = parse_attachments(attachments or [])
        inline_images = await load_image_bytes(object_storage, images) if images else {}

        payment_html, payment_plain, qr_png = build_payment_block(
            payment_info_from_owner(owner),
            amount=amount_due,
            memo=invoice.invoice_number,
            with_qr=not inline_images,
        )
        if qr_png is not None:
            inline_images["vietqr"] = qr_png

        content = build_invoice_email(
            client_name=client.name,
            freelancer_name=getattr(owner, "full_name", None),
            invoice_number=invoice.invoice_number,
            line_items=[(i.description, Decimal(i.quantity) * Decimal(i.unit_price)) for i in items]
            or [("Thanh toán theo hợp đồng", Decimal(invoice.subtotal or 0))],
            total=Decimal(invoice.total or 0),
            amount_due=amount_due,
            issue_date=invoice.issue_date,
            due_date=invoice.due_date,
            notes=invoice.notes,
            payment_html=payment_html,
            payment_plain=payment_plain,
            images_html=images_html(images, {f"img{i}": f"cid:img{i}" for i in range(len(images))}),
            footer=build_footer(
                getattr(owner, "full_name", None),
                getattr(owner, "email", None),
                f"Hóa đơn {invoice.invoice_number}",
            ),
        )
        return content, inline_images, client.email

    async def send(
        self,
        user_id: uuid.UUID,
        invoice_id: uuid.UUID,
        *,
        notify: bool = True,
        attachments: list[dict[str, str]] | None = None,
    ):
        """Gửi hóa đơn cho khách và đánh dấu đã gửi.

        `notify=False` chỉ ĐÁNH DẤU, không gửi thư — dành cho freelancer đã tự gửi tay qua
        Zalo/Messenger rồi chỉ muốn hệ thống ghi nhận.

        **Gửi hỏng thì KHÔNG đánh dấu đã gửi.** Trước đây hàm này chỉ đổi trạng thái và
        không hề gửi thư, nên nút "Gửi cho khách" là một lời nói dối: khách không nhận được
        gì mà hệ thống vẫn ghi "đã gửi". Nay nếu thư không đi được thì hóa đơn ở nguyên
        `draft` và lỗi nổi lên kèm lý do (`EmailDeliveryError`) — thà để freelancer biết mà
        gửi lại, còn hơn để họ yên tâm ngồi đợi một khoản tiền mà khách không biết là phải
        trả.  #Huynh
        """
        from src.shared.email.smtp import send_email

        invoice = await self._get_invoice(user_id, invoice_id)
        if invoice.status != "draft":
            raise BusinessRuleError("Only draft invoices can be sent")

        # Token sinh TRƯỚC khi gửi: nếu sau này thân thư có kèm link xem hóa đơn thì link đó
        # phải có sẵn lúc dựng thư, không thể vá vào sau.
        share_token = invoice.share_token or secrets.token_urlsafe(32)

        if notify:
            content, inline_images, to_email = await self._build_invoice_email(
                invoice, attachments
            )
            owner = await self.repo.get_owner(invoice.owner_user_id)
            await send_email(
                to=to_email,
                subject=content.subject,
                html=content.html,
                plain=content.plain,
                from_name=getattr(owner, "full_name", None),
                reply_to=getattr(owner, "email", None),
                inline_images=inline_images or None,
            )

        invoice.status = "sent"
        invoice.sent_at = datetime.now(UTC)
        invoice.share_token = share_token
        return await self.repo.save(invoice)

    async def void(self, user_id: uuid.UUID, invoice_id: uuid.UUID):
        invoice = await self._get_invoice(user_id, invoice_id)
        if invoice.status == "void" or invoice.amount_paid > 0:
            raise BusinessRuleError("Invoices with recorded payments cannot be voided")
        invoice.status = "void"
        invoice.voided_at = datetime.now(UTC)
        return await self.repo.save(invoice)

    async def record_payment(
        self, user_id: uuid.UUID, invoice_id: uuid.UUID, payload: PaymentRequest
    ):
        invoice = await self._get_invoice(user_id, invoice_id)
        if payload.amount <= 0:
            raise BusinessRuleError("Payment amount must be greater than zero")
        if invoice.status in ("draft", "void"):
            raise BusinessRuleError("Cannot record payment for draft or void invoice")
        if invoice.amount_paid + payload.amount > invoice.total:
            raise BusinessRuleError("Payment would exceed invoice total")
        await self.repo.add_payment(
            invoice_id=invoice_id,
            amount=payload.amount,
            payment_date=payload.payment_date,
            payment_method=payload.payment_method,
            reference_note=payload.reference_note,
        )
        invoice.amount_paid += payload.amount
        invoice.status = "paid" if invoice.amount_paid == invoice.total else "partially_paid"
        return await self.repo.save(invoice)

    async def list_payments(self, user_id: uuid.UUID, invoice_id: uuid.UUID) -> list:
        await self._get_invoice(user_id, invoice_id)
        return await self.repo.list_payments(invoice_id)

    async def get_public_view(self, share_token: str):
        invoice = await self.repo.get_public_by_token(share_token)
        if invoice is None:
            raise NotFoundError("Invoice not found or link is invalid")
        return invoice
