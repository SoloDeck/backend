"""Contracts application service."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.contracts.domain.value_objects.contract_status import (
    CONTRACT_TRANSITIONS,
    TERMINAL_CONTRACT_STATUSES,
    ContractStatus,
)
from src.modules.contracts.infrastructure.repository import ContractsRepository
from src.modules.contracts.schemas.request import ContractRequest
from src.shared.exceptions.domain import (
    BusinessRuleError,
    EntitlementError,
    InvalidStateTransitionError,
    NotFoundError,
)


@dataclass
class ContractsService:
    db: AsyncSession
    repo: ContractsRepository | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = ContractsRepository(self.db)

    async def _get_contract(self, user_id: uuid.UUID, contract_id: uuid.UUID):  # type: ignore[return]
        contract = await self.repo.get_by_id(contract_id, user_id)
        if contract is None:
            raise NotFoundError(f"Contract {contract_id} not found")
        return contract

    async def create(self, user_id: uuid.UUID, payload: ContractRequest):  # type: ignore[return]
        proposal = await self.repo.get_proposal(payload.proposal_id)
        if proposal is None:
            raise NotFoundError(f"Proposal {payload.proposal_id} not found")
        if proposal.status != "accepted":
            raise BusinessRuleError(
                f"Contract can only be created from an accepted proposal "
                f"(current status: '{proposal.status}')"
            )

        version_number = await self.repo.count_by_deal(payload.deal_id) + 1

        client = await self.repo.get_client(payload.client_id)
        client_snapshot: dict = {}
        if client is not None:
            client_snapshot = {
                "id": str(client.id),
                "name": client.name,
                "email": client.email,
                "phone": client.phone,
            }

        return await self.repo.create(
            deal_id=payload.deal_id,
            proposal_id=payload.proposal_id,
            client_id=payload.client_id,
            owner_user_id=user_id,
            version_number=version_number,
            status="draft",
            content=payload.content,
            client_snapshot=client_snapshot,
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

    async def get_one(self, user_id: uuid.UUID, contract_id: uuid.UUID):  # type: ignore[return]
        return await self._get_contract(user_id, contract_id)

    async def update(self, user_id: uuid.UUID, contract_id: uuid.UUID, payload: ContractRequest):  # type: ignore[return]
        contract = await self._get_contract(user_id, contract_id)
        if contract.status != "draft":
            raise BusinessRuleError(
                f"Contract content can only be edited in draft status "
                f"(current status: '{contract.status}')"
            )
        if payload.content:
            contract.content = payload.content
        return await self.repo.save(contract)

    async def transition_status(
        self, user_id: uuid.UUID, contract_id: uuid.UUID, target_status: str
    ):  # type: ignore[return]
        contract = await self._get_contract(user_id, contract_id)

        try:
            current = ContractStatus(contract.status)
            target = ContractStatus(target_status)
        except ValueError:
            raise BusinessRuleError(f"'{target_status}' is not a valid contract status") from None

        if target not in CONTRACT_TRANSITIONS[current]:
            raise InvalidStateTransitionError("contract", current.value, target.value)

        now = datetime.now(UTC)
        contract.status = target.value

        if target == ContractStatus.ACTIVE:
            contract.signed_by_freelancer_at = now
        elif target == ContractStatus.PENDING_SIGNATURES or target in TERMINAL_CONTRACT_STATUSES:
            pass

        return await self.repo.save(contract)

    async def amend(self, user_id: uuid.UUID, contract_id: uuid.UUID, payload: ContractRequest):  # type: ignore[return]
        contract = await self._get_contract(user_id, contract_id)
        if contract.status != ContractStatus.ACTIVE:
            raise BusinessRuleError(
                f"Only active contracts can be amended (current status: '{contract.status}')"
            )

        new_version = await self.repo.count_by_deal(contract.deal_id) + 1

        new_contract = await self.repo.create(
            deal_id=contract.deal_id,
            proposal_id=contract.proposal_id,
            client_id=contract.client_id,
            owner_user_id=user_id,
            version_number=new_version,
            status=ContractStatus.DRAFT,
            content=payload.content if payload.content else contract.content,
            client_snapshot=contract.client_snapshot,
            parent_contract_id=contract.id,
        )
        contract.status = ContractStatus.ARCHIVED
        await self.repo.save(contract)
        return new_contract

    async def generate_content(self, user_id: uuid.UUID, contract_id: uuid.UUID, ai_facade):  # type: ignore[return]
        contract = await self._get_contract(user_id, contract_id)
        if contract.status != ContractStatus.DRAFT:
            raise BusinessRuleError(
                f"AI generation is only available for draft contracts (current status: '{contract.status}')"
            )

        sub = await self.repo.get_subscription(user_id)
        plan = await self.repo.get_plan(sub.plan_id) if sub else None
        user_can_use_ai = bool(plan and plan.can_use_ai)

        deal = await self.repo.get_deal(contract.deal_id)
        proposal = await self.repo.get_proposal(contract.proposal_id)
        client = await self.repo.get_client(contract.client_id)
        user = await self.repo.get_user(user_id)

        content = await ai_facade.generate_contract(
            deal_data={"title": deal.title if deal else "", "stage": deal.stage if deal else ""},
            proposal_content=proposal.content if proposal else {},
            client_data={
                "name": client.name if client else "",
                "email": client.email if client else "",
            },
            user_profile={
                "name": user.full_name if user else "",
                "email": user.email if user else "",
            },
            user_can_use_ai=user_can_use_ai,
        )
        contract.content = content
        contract.ai_generated = True
        return await self.repo.save(contract)

    async def send(self, user_id: uuid.UUID, contract_id: uuid.UUID):  # type: ignore[return]
        return await self.transition_status(user_id, contract_id, "pending_signatures")

    async def sign(self, user_id: uuid.UUID, contract_id: uuid.UUID):  # type: ignore[return]
        contract = await self._get_contract(user_id, contract_id)
        if contract.status != ContractStatus.PENDING_SIGNATURES:
            raise BusinessRuleError(
                f"Contract must be in pending_signatures status to sign "
                f"(current status: '{contract.status}')"
            )
        now = datetime.now(UTC)
        contract.signed_by_freelancer_at = now
        if contract.signed_by_client_at is not None:
            contract.status = ContractStatus.ACTIVE
        return await self.repo.save(contract)

    async def terminate(self, user_id: uuid.UUID, contract_id: uuid.UUID):  # type: ignore[return]
        return await self.transition_status(user_id, contract_id, "terminated")

    async def export_pdf(self, user_id: uuid.UUID, contract_id: uuid.UUID) -> dict:
        from src.workers.pdf_jobs.tasks import render_contract_pdf

        contract = await self._get_contract(user_id, contract_id)

        sub = await self.repo.get_subscription(user_id)
        if sub is None:
            raise EntitlementError("No active subscription found", "can_export_pdf")
        plan = await self.repo.get_plan(sub.plan_id)
        if plan is None or not plan.can_export_pdf:
            raise EntitlementError(
                "Your subscription plan does not include PDF export", "can_export_pdf"
            )

        task = render_contract_pdf.delay(str(contract.id))
        return {"status": "pending", "task_id": task.id, "download_url": None}

    async def delete(self, user_id: uuid.UUID, contract_id: uuid.UUID) -> None:
        contract = await self._get_contract(user_id, contract_id)
        if contract.status not in ("draft", "expired"):
            raise BusinessRuleError(
                f"Only draft or expired contracts can be deleted "
                f"(current status: '{contract.status}')"
            )
        await self.repo.delete(contract)
