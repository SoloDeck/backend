"""Contracts application service."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.contracts.schemas.request import ContractRequest
from src.modules.contracts.domain.value_objects.contract_status import (
    CONTRACT_TRANSITIONS,
    TERMINAL_CONTRACT_STATUSES,
    ContractStatus,
)
from src.shared.exceptions.domain import (
    BusinessRuleError,
    EntitlementError,
    InvalidStateTransitionError,
    NotFoundError,
)


@dataclass
class ContractsService:
    db: AsyncSession

    async def _get_contract(self, user_id: uuid.UUID, contract_id: uuid.UUID):  # type: ignore[return]
        from src.infrastructure.database.models import ContractModel

        contract = await self.db.scalar(
            select(ContractModel).where(
                ContractModel.id == contract_id,
                ContractModel.owner_user_id == user_id,
            )
        )
        if contract is None:
            raise NotFoundError(f"Contract {contract_id} not found")
        return contract

    async def create(self, user_id: uuid.UUID, payload: ContractRequest):  # type: ignore[return]
        from src.infrastructure.database.models import ClientModel, ContractModel, ProposalModel

        proposal = await self.db.scalar(
            select(ProposalModel).where(ProposalModel.id == payload.proposal_id)
        )
        if proposal is None:
            raise NotFoundError(f"Proposal {payload.proposal_id} not found")
        if proposal.status != "accepted":
            raise BusinessRuleError(
                f"Contract can only be created from an accepted proposal "
                f"(current status: '{proposal.status}')"
            )

        count_result = await self.db.scalar(
            select(func.count()).select_from(ContractModel).where(
                ContractModel.deal_id == payload.deal_id
            )
        )
        version_number = (count_result or 0) + 1

        client = await self.db.scalar(
            select(ClientModel).where(ClientModel.id == payload.client_id)
        )
        client_snapshot: dict = {}
        if client is not None:
            client_snapshot = {
                "id": str(client.id),
                "name": client.name,
                "email": client.email,
                "phone": client.phone,
            }

        contract = ContractModel(
            deal_id=payload.deal_id,
            proposal_id=payload.proposal_id,
            client_id=payload.client_id,
            owner_user_id=user_id,
            version_number=version_number,
            status="draft",
            content=payload.content,
            client_snapshot=client_snapshot,
        )
        self.db.add(contract)
        await self.db.flush()
        await self.db.refresh(contract)
        return contract

    async def list_all(
        self,
        user_id: uuid.UUID,
        status: str | None = None,
        deal_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list, int]:
        from src.infrastructure.database.models import ContractModel

        conditions = [ContractModel.owner_user_id == user_id]
        if status is not None:
            conditions.append(ContractModel.status == status)
        if deal_id is not None:
            conditions.append(ContractModel.deal_id == deal_id)

        total = await self.db.scalar(
            select(func.count()).select_from(ContractModel).where(*conditions)
        ) or 0
        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(ContractModel)
            .where(*conditions)
            .order_by(ContractModel.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

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
        await self.db.flush()
        await self.db.refresh(contract)
        return contract

    async def transition_status(
        self, user_id: uuid.UUID, contract_id: uuid.UUID, target_status: str
    ):  # type: ignore[return]
        contract = await self._get_contract(user_id, contract_id)

        try:
            current = ContractStatus(contract.status)
            target = ContractStatus(target_status)
        except ValueError:
            raise BusinessRuleError(f"'{target_status}' is not a valid contract status")

        if target not in CONTRACT_TRANSITIONS[current]:
            raise InvalidStateTransitionError("contract", current.value, target.value)

        now = datetime.now(UTC)
        contract.status = target.value

        if target == ContractStatus.ACTIVE:
            contract.signed_by_freelancer_at = now
        elif target == ContractStatus.PENDING_SIGNATURES:
            pass  # no extra timestamp
        elif target in TERMINAL_CONTRACT_STATUSES:
            pass  # no extra timestamp beyond what's set above

        await self.db.flush()
        await self.db.refresh(contract)
        return contract

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
        await self.db.flush()
        await self.db.refresh(contract)
        return contract

    async def terminate(self, user_id: uuid.UUID, contract_id: uuid.UUID):  # type: ignore[return]
        return await self.transition_status(user_id, contract_id, "terminated")

    async def export_pdf(self, user_id: uuid.UUID, contract_id: uuid.UUID) -> dict:
        from src.infrastructure.database.models import PlanModel, SubscriptionModel
        from src.workers.pdf_jobs.tasks import render_contract_pdf

        contract = await self._get_contract(user_id, contract_id)

        sub = await self.db.scalar(
            select(SubscriptionModel).where(SubscriptionModel.user_id == user_id)
        )
        if sub is None:
            raise EntitlementError("No active subscription found", "can_export_pdf")
        plan = await self.db.scalar(select(PlanModel).where(PlanModel.id == sub.plan_id))
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
        await self.db.delete(contract)
        await self.db.flush()