"""Seed subscription plans: Free, Pro, Agency."""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import text

from .base import BaseSeeder


@dataclass(frozen=True)
class _PlanDef:
    name: str
    slug: str
    price_monthly: Decimal
    currency: str
    max_ai_generations_per_month: int
    can_use_ai: bool
    can_export_pdf: bool
    max_clients: int | None
    max_deals: int | None


_PLANS: list[_PlanDef] = [
    _PlanDef(
        name="Free",
        slug="free",
        price_monthly=Decimal("0"),
        currency="VND",
        max_ai_generations_per_month=0,
        can_use_ai=False,
        can_export_pdf=False,
        max_clients=10,
        max_deals=10,
    ),
    _PlanDef(
        name="Pro",
        slug="pro",
        price_monthly=Decimal("199000"),
        currency="VND",
        max_ai_generations_per_month=50,
        can_use_ai=True,
        can_export_pdf=True,
        max_clients=None,  # unlimited
        max_deals=None,
    ),
    _PlanDef(
        name="Agency",
        slug="agency",
        price_monthly=Decimal("599000"),
        currency="VND",
        max_ai_generations_per_month=500,
        can_use_ai=True,
        can_export_pdf=True,
        max_clients=None,
        max_deals=None,
    ),
]

_INSERT_IF_MISSING = text("""
    INSERT INTO subscription_plans (
        name, slug, price_monthly, currency,
        max_ai_generations_per_month, can_use_ai, can_export_pdf,
        max_clients, max_deals, is_active
    ) VALUES (
        :name, :slug, :price_monthly, :currency,
        :max_ai_generations_per_month, :can_use_ai, :can_export_pdf,
        :max_clients, :max_deals, TRUE
    )
    ON CONFLICT (slug) DO NOTHING
    """)


class PlansSeeder(BaseSeeder):
    name = "plans"

    async def run(self) -> None:
        self._log.info("seeder.start", plans=[p.slug for p in _PLANS])
        for plan in _PLANS:
            await self.db.execute(
                _INSERT_IF_MISSING,
                {
                    "name": plan.name,
                    "slug": plan.slug,
                    "price_monthly": plan.price_monthly,
                    "currency": plan.currency,
                    "max_ai_generations_per_month": plan.max_ai_generations_per_month,
                    "can_use_ai": plan.can_use_ai,
                    "can_export_pdf": plan.can_export_pdf,
                    "max_clients": plan.max_clients,
                    "max_deals": plan.max_deals,
                },
            )
        await self._commit()
        self._log.info("seeder.done", count=len(_PLANS))
