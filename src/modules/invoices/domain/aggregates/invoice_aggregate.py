import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from src.modules.invoices.domain.entities.invoice import Invoice
from src.modules.invoices.domain.entities.invoice_line_item import InvoiceLineItem
from src.modules.invoices.domain.entities.payment_record import PaymentMethod, PaymentRecord
from src.modules.invoices.domain.events.invoice_events import (
    InvoiceCreatedEvent,
    InvoiceOverdueEvent,
    InvoicePaidEvent,
    InvoiceSentEvent,
    PaymentRecordedEvent,
)
from src.modules.invoices.domain.exceptions.exceptions import (
    InvoiceEditForbiddenError,
    StandaloneInvoiceError,
)
from src.modules.invoices.domain.value_objects.invoice_status import InvoiceStatus
from src.shared.domain.base import DomainEvent
from src.shared.domain.value_objects.money import Money


@dataclass
class InvoiceAggregate:
    invoice: Invoice
    line_items: list[InvoiceLineItem] = field(default_factory=list)
    payment_records: list[PaymentRecord] = field(default_factory=list)
    _pending_events: list[DomainEvent] = field(
        default_factory=list, init=False, repr=False, compare=False
    )

    @classmethod
    def create(
        cls,
        owner_user_id: uuid.UUID,
        client_id: uuid.UUID,
        invoice_number: str,
        currency: str,
        due_date: datetime,
        deal_id: uuid.UUID | None = None,
        contract_id: uuid.UUID | None = None,
        notes: str | None = None,
    ) -> "InvoiceAggregate":
        if deal_id is None and contract_id is None:
            raise StandaloneInvoiceError()
        now = datetime.now(UTC)
        invoice_id = uuid.uuid4()
        zero = Money.zero(currency)
        invoice = Invoice(
            id=invoice_id,
            owner_user_id=owner_user_id,
            deal_id=deal_id,
            contract_id=contract_id,
            client_id=client_id,
            invoice_number=invoice_number,
            status=InvoiceStatus.DRAFT,
            subtotal=zero,
            tax_amount=zero,
            total=zero,
            amount_paid=zero,
            currency=currency,
            issue_date=now,
            due_date=due_date,
            paid_at=None,
            notes=notes,
            share_token=None,
            share_token_expires_at=None,
            created_at=now,
            updated_at=now,
        )
        agg = cls(invoice=invoice)
        agg._pending_events.append(
            InvoiceCreatedEvent(
                event_id=uuid.uuid4(),
                aggregate_id=invoice_id,
                occurred_at=now,
                deal_id=deal_id,
                contract_id=contract_id,
                owner_user_id=owner_user_id,
            )
        )
        return agg

    def add_line_item(
        self, description: str, quantity: Decimal, unit_price: Money
    ) -> InvoiceLineItem:
        if self.invoice.status != InvoiceStatus.DRAFT:
            raise InvoiceEditForbiddenError(self.invoice.status)
        item = InvoiceLineItem(
            id=uuid.uuid4(),
            invoice_id=self.invoice.id,
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            sort_order=len(self.line_items) + 1,
        )
        self.line_items.append(item)
        self._recalculate_subtotal()
        return item

    def remove_line_item(self, line_item_id: uuid.UUID) -> None:
        if self.invoice.status != InvoiceStatus.DRAFT:
            raise InvoiceEditForbiddenError(self.invoice.status)
        self.line_items = [i for i in self.line_items if i.id != line_item_id]
        self._recalculate_subtotal()

    def set_tax(self, tax_amount: Money) -> None:
        if self.invoice.status != InvoiceStatus.DRAFT:
            raise InvoiceEditForbiddenError(self.invoice.status)
        self.invoice.tax_amount = tax_amount
        self.invoice.total = self.invoice.subtotal.add(tax_amount)
        self.invoice.updated_at = datetime.now(UTC)

    def send(self) -> None:
        self.invoice.send()
        self._pending_events.append(
            InvoiceSentEvent(
                event_id=uuid.uuid4(),
                aggregate_id=self.invoice.id,
                occurred_at=self.invoice.updated_at,
                owner_user_id=self.invoice.owner_user_id,
                total=self.invoice.total,
            )
        )

    def record_payment(
        self,
        amount: Money,
        method: PaymentMethod,
        reference: str | None = None,
        note: str | None = None,
    ) -> PaymentRecord:
        self.invoice.apply_payment(amount)
        record = PaymentRecord(
            id=uuid.uuid4(),
            invoice_id=self.invoice.id,
            amount=amount,
            method=method,
            reference=reference,
            note=note,
            recorded_at=self.invoice.updated_at,
        )
        self.payment_records.append(record)
        now = self.invoice.updated_at
        self._pending_events.append(
            PaymentRecordedEvent(
                event_id=uuid.uuid4(),
                aggregate_id=self.invoice.id,
                occurred_at=now,
                amount_paid=self.invoice.amount_paid,
                remaining=self.invoice.remaining_balance,
            )
        )
        if self.invoice.is_fully_paid:
            self._pending_events.append(
                InvoicePaidEvent(
                    event_id=uuid.uuid4(),
                    aggregate_id=self.invoice.id,
                    occurred_at=now,
                    deal_id=self.invoice.deal_id,
                    owner_user_id=self.invoice.owner_user_id,
                )
            )
        return record

    def mark_overdue(self) -> None:
        self.invoice.mark_overdue()
        self._pending_events.append(
            InvoiceOverdueEvent(
                event_id=uuid.uuid4(),
                aggregate_id=self.invoice.id,
                occurred_at=self.invoice.updated_at,
                deal_id=self.invoice.deal_id,
                owner_user_id=self.invoice.owner_user_id,
            )
        )

    def _recalculate_subtotal(self) -> None:
        if not self.line_items:
            self.invoice.subtotal = Money.zero(self.invoice.currency)
        else:
            total = Money.zero(self.invoice.currency)
            for item in self.line_items:
                total = total.add(item.line_total)
            self.invoice.subtotal = total
        self.invoice.total = self.invoice.subtotal.add(self.invoice.tax_amount)
        self.invoice.updated_at = datetime.now(UTC)

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._pending_events)
        self._pending_events.clear()
        return events
