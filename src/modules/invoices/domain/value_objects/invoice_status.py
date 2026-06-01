from enum import Enum


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    OVERDUE = "overdue"
    VOID = "void"


TERMINAL_INVOICE_STATUSES: frozenset[InvoiceStatus] = frozenset(
    {InvoiceStatus.PAID, InvoiceStatus.VOID}
)
