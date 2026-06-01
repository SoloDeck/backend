from src.modules.invoices.domain.value_objects.invoice_status import InvoiceStatus


class InvoiceDomainError(Exception):
    """Base for all Invoice domain errors."""


class InvoiceEditForbiddenError(InvoiceDomainError):
    def __init__(self, status: InvoiceStatus) -> None:
        super().__init__(f"Invoice cannot be edited in status '{status.value}'")


class TerminalInvoiceError(InvoiceDomainError):
    def __init__(self, status: InvoiceStatus) -> None:
        super().__init__(f"Invoice is in terminal status '{status.value}'")


class OverpaymentError(InvoiceDomainError):
    def __init__(self) -> None:
        super().__init__("Payment would exceed invoice total")


class InvalidInvoiceTotalError(InvoiceDomainError):
    def __init__(self) -> None:
        super().__init__("total must equal subtotal + tax_amount before invoice can be sent")


class StandaloneInvoiceError(InvoiceDomainError):
    def __init__(self) -> None:
        super().__init__("Invoice must be linked to a contract_id or deal_id")
