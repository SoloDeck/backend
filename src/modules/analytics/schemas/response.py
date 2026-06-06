from decimal import Decimal

from pydantic import BaseModel


class DashboardResponse(BaseModel):
    total_clients: int
    active_deals: int
    total_revenue: Decimal
    pending_invoices: int
