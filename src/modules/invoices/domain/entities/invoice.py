import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from src.modules.invoices.domain.value_objects.invoice_status import (
    TERMINAL_INVOICE_STATUSES,
    InvoiceStatus,
)
from src.shared.domain.value_objects.money import Money


@dataclass
class Invoice:
    id: uuid.UUID
    owner_user_id: uuid.UUID
    deal_id: uuid.UUID | None       # at least one of deal_id / contract_id required
    contract_id: uuid.UUID | None
    client_id: uuid.UUID
    invoice_number: str
    status: InvoiceStatus
    subtotal: Money
    tax_amount: Money
    total: Money
    amount_paid: Money
    currency: str
    issue_date: datetime
    due_date: datetime
    paid_at: datetime | None
    notes: str | None
    share_token: str | None
    share_token_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime

    # ------------------------------------------------------------------ #
    # Queries                                                              #
    # ------------------------------------------------------------------ #

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_INVOICE_STATUSES

    @property
    def remaining_balance(self) -> Money:
        return self.total.subtract(self.amount_paid)

    @property
    def is_fully_paid(self) -> bool:
        return self.amount_paid.amount >= self.total.amount

    def validate_total(self) -> bool:
        return self.subtotal.add(self.tax_amount).amount == self.total.amount

    # ------------------------------------------------------------------ #
    # Commands                                                             #
    # ------------------------------------------------------------------ #

    def send(self) -> None:
        from src.modules.invoices.domain.exceptions.exceptions import (
            InvalidInvoiceTotalError,
            InvoiceEditForbiddenError,
        )
        if self.status != InvoiceStatus.DRAFT:
            raise InvoiceEditForbiddenError(self.status)
        if not self.validate_total():
            raise InvalidInvoiceTotalError()
        self.status = InvoiceStatus.SENT
        self.updated_at = datetime.now(UTC)

    def apply_payment(self, amount: Money) -> None:
        from src.modules.invoices.domain.exceptions.exceptions import (
            OverpaymentError,
            TerminalInvoiceError,
        )
        if self.is_terminal:
            raise TerminalInvoiceError(self.status)
        new_paid = self.amount_paid.add(amount)
        if new_paid.amount > self.total.amount:
            raise OverpaymentError()
        self.amount_paid = new_paid
        now = datetime.now(UTC)
        if self.is_fully_paid:
            self.status = InvoiceStatus.PAID
            self.paid_at = now
        else:
            self.status = InvoiceStatus.PARTIALLY_PAID
        self.updated_at = now

    def mark_overdue(self) -> None:
        if self.status in {InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID}:
            self.status = InvoiceStatus.OVERDUE
            self.updated_at = datetime.now(UTC)

    def void(self) -> None:
        from src.modules.invoices.domain.exceptions.exceptions import TerminalInvoiceError
        if self.status == InvoiceStatus.PAID:
            raise TerminalInvoiceError(self.status)
        self.status = InvoiceStatus.VOID
        self.updated_at = datetime.now(UTC)
