"""Proposals application service."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, date

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.proposals.infrastructure.repository import ProposalsRepository
from src.modules.proposals.schemas.request import ProposalRequest
from src.shared.events.bus import event_bus
from src.shared.exceptions.domain import (
    BusinessRuleError,
    InvalidStateTransitionError,
    NotFoundError,
)

from src.ai.proposal_generator.application.render import ProposalPdfRenderer
from src.modules.proposals.application.pdf_content import build_proposal_document

_VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"sent"}),
    "sent": frozenset({"accepted", "rejected", "expired"}),
    "accepted": frozenset(),
    "rejected": frozenset(),
    "expired": frozenset(),
    "superseded": frozenset(),
}


@dataclass
class ProposalsService:
    db: AsyncSession
    repo: ProposalsRepository | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = ProposalsRepository(self.db)

    async def _get_proposal(self, user_id: uuid.UUID, proposal_id: uuid.UUID):  # type: ignore[return]
        proposal = await self.repo.get_by_id(proposal_id, user_id)
        if proposal is None:
            raise NotFoundError(f"Proposal {proposal_id} not found")
        return proposal

    async def create(self, user_id: uuid.UUID, payload: ProposalRequest, *, ai_generated: bool = False):  # type: ignore[return]
        deal = await self.repo.get_deal(payload.deal_id)
        if deal is None or deal.owner_user_id != user_id:
            raise NotFoundError(f"Deal {payload.deal_id} not found")
        version_number = await self.repo.count_by_deal(payload.deal_id) + 1
        return await self.repo.create(
            deal_id=payload.deal_id,
            owner_user_id=user_id,
            version_number=version_number,
            status=payload.status,
            content=payload.content,
            ai_generated=ai_generated,
        )

    async def list_all(
        self,
        user_id: uuid.UUID,
        status: str | None = None,
        deal_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list, int]:
        return await self.repo.list_all(
            user_id, status=status, deal_id=deal_id, page=page, page_size=page_size
        )

    async def get_one(self, user_id: uuid.UUID, proposal_id: uuid.UUID):  # type: ignore[return]
        return await self._get_proposal(user_id, proposal_id)

    async def update(self, user_id: uuid.UUID, proposal_id: uuid.UUID, payload: ProposalRequest):  # type: ignore[return]
        proposal = await self._get_proposal(user_id, proposal_id)
        if proposal.status != "draft":
            raise BusinessRuleError(
                f"Proposal content can only be edited in draft status "
                f"(current status: '{proposal.status}')"
            )
        if payload.content:
            proposal.content = payload.content
        return await self.repo.save(proposal)

    async def delete(self, user_id: uuid.UUID, proposal_id: uuid.UUID) -> None:
        proposal = await self._get_proposal(user_id, proposal_id)
        await self.repo.delete(proposal)

    async def generate_content(self, user_id: uuid.UUID, proposal_id: uuid.UUID, ai_facade):  # type: ignore[return]
        proposal = await self._get_proposal(user_id, proposal_id)
        if proposal.status != "draft":
            raise BusinessRuleError(
                f"AI generation is only available for draft proposals (current status: '{proposal.status}')"
            )

        sub = await self.repo.get_subscription(user_id)
        plan = await self.repo.get_plan(sub.plan_id) if sub else None
        user_can_use_ai = bool(plan and plan.can_use_ai)

        deal = await self.repo.get_deal(proposal.deal_id)
        client = await self.repo.get_client(deal.client_id) if deal else None
        user = await self.repo.get_user(user_id)

        budget = None
        if deal and deal.estimated_value is not None:
            budget = f"{deal.estimated_value} {deal.currency or 'VND'}"

        company_name = None
        if client and getattr(client, "type", None) == "company":
            company_name = client.name

        content = await ai_facade.generate_proposal(
            deal_data={
                "title": deal.title if deal else "",
                "stage": deal.stage if deal else "",
                "notes": deal.notes if deal else "",
                "project_type": deal.project_type if deal else None,
                "service_category": deal.service_category if deal else None,
                "pricing_tier": deal.pricing_tier if deal else None,
                "budget": budget,
            },
            client_data={
                "name": client.name if client else "",
                "company_name": company_name,
                "email": client.email if client else "",
            },
            user_profile={
                "name": user.full_name if user else "",
                "email": user.email if user else "",
            },
            template=None,
            user_can_use_ai=user_can_use_ai,
        )
        proposal.content = content
        proposal.ai_generated = True
        return await self.repo.save(proposal)

    async def generate_from_deal(self, user_id: uuid.UUID, deal_id: uuid.UUID, ai_facade):  # type: ignore[return]
        deal = await self.repo.get_deal(deal_id)
        if deal is None or deal.owner_user_id != user_id:
            raise NotFoundError(f"Deal {deal_id} not found")

        sub = await self.repo.get_subscription(user_id)
        plan = await self.repo.get_plan(sub.plan_id) if sub else None
        user_can_use_ai = bool(plan and plan.can_use_ai)

        client = await self.repo.get_client(deal.client_id) if deal.client_id else None
        user = await self.repo.get_user(user_id)

        budget = None
        if deal.estimated_value is not None:
            budget = f"{deal.estimated_value} {deal.currency or 'VND'}"

        company_name = None
        if client and getattr(client, "type", None) == "company":
            company_name = client.name

        content = await ai_facade.generate_proposal(
            deal_data={
                "title": deal.title,
                "stage": deal.stage,
                "notes": deal.notes,
                "project_type": deal.project_type,
                "service_category": deal.service_category,
                "pricing_tier": deal.pricing_tier,
                "budget": budget,
            },
            client_data={
                "name": client.name if client else "",
                "company_name": company_name,
                "email": client.email if client else "",
            },
            user_profile={
                "name": user.full_name if user else "",
                "email": user.email if user else "",
            },
            template=None,
            user_can_use_ai=user_can_use_ai,
        )

        version_number = await self.repo.count_by_deal(deal_id) + 1
        return await self.repo.create(
            deal_id=deal_id,
            owner_user_id=user_id,
            version_number=version_number,
            status="draft",
            content=content,
            ai_generated=True,
        )

    async def generate_pdf(
            self,
            user_id: uuid.UUID,
            proposal_id: uuid.UUID,
    ) -> bytes:

        proposal = await self._get_proposal(user_id, proposal_id)

        deal = await self.repo.get_deal(proposal.deal_id)
        if deal is None:
            raise NotFoundError(f"Deal {proposal.deal_id} not found")

        client = await self.repo.get_client(deal.client_id) if deal.client_id else None
        user = await self.repo.get_user(user_id)

        company_name = None
        if client and getattr(client, "type", None) == "company":
            company_name = client.name

        # Trước đây chỗ này index cứng: proposal.content["project_overview"], ...
        # Nó chỉ đọc được shape nội bộ của AI, và dùng [...] chứ không .get() nên
        # thiếu MỘT khoá là KeyError → 500. Mọi báo giá do frontend tạo/sửa đều
        # không xuất được PDF — dù frontend lưu ĐÚNG shape ProposalContentDTO mà
        # contracts/openapi.yaml khai. Giờ đọc được cả hai shape.  #Huynh
        document = build_proposal_document(
            proposal.content,
            freelancer_name=user.full_name if user else "",
            client_name=client.name if client else "",
            company_name=company_name,
            project_type=deal.project_type or "",
            proposal_date=str(date.today()),
        )

        renderer = ProposalPdfRenderer()

        return renderer.render_pdf(document)

    async def transition_status(
        self, user_id: uuid.UUID, proposal_id: uuid.UUID, target_status: str
    ):  # type: ignore[return]
        proposal = await self._get_proposal(user_id, proposal_id)
        current = proposal.status
        allowed = _VALID_TRANSITIONS.get(current, frozenset())
        if target_status not in allowed:
            raise InvalidStateTransitionError("proposal", current, target_status)

        now = datetime.now(UTC)

        if target_status == "sent":
            existing = await self.repo.get_sent_by_deal(proposal.deal_id, proposal_id)
            if existing is not None:
                existing.status = "superseded"
            proposal.sent_at = now

        if target_status in ("accepted", "rejected", "expired"):
            proposal.responded_at = now

        proposal.status = target_status
        await self.repo.save(proposal)

        if target_status == "accepted":
            await event_bus.publish(
                "proposals.proposal_accepted",
                {
                    "proposal_id": str(proposal_id),
                    "deal_id": str(proposal.deal_id),
                    "owner_user_id": str(user_id),
                },
            )
        elif target_status == "sent":
            await event_bus.publish(
                "proposals.proposal_sent",
                {
                    "proposal_id": str(proposal_id),
                    "deal_id": str(proposal.deal_id),
                    "owner_user_id": str(user_id),
                },
            )

        return proposal
