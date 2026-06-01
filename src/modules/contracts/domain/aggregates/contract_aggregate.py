import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.shared.domain.base import DomainEvent
from src.shared.domain.value_objects.money import Money
from src.modules.contracts.domain.entities.contract import Contract
from src.modules.contracts.domain.entities.contract_version import ContractVersion
from src.modules.contracts.domain.entities.payment_milestone import PaymentMilestone
from src.modules.contracts.domain.value_objects.contract_status import ContractStatus
from src.modules.contracts.domain.events.contract_events import (
    ContractCreatedEvent,
    ContractSignedEvent,
    ContractMilestoneReachedEvent,
    ContractCompletedEvent,
    ContractTerminatedEvent,
)


@dataclass
class ContractAggregate:
    contract: Contract
    versions: list[ContractVersion] = field(default_factory=list)
    milestones: list[PaymentMilestone] = field(default_factory=list)
    _pending_events: list[DomainEvent] = field(
        default_factory=list, init=False, repr=False, compare=False
    )

    @classmethod
    def create(
        cls,
        deal_id: uuid.UUID,
        proposal_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        title: str,
        content: dict[str, object],
        client_snapshot: dict[str, object],
        ai_generated: bool = False,
    ) -> "ContractAggregate":
        now = datetime.now(timezone.utc)
        contract_id = uuid.uuid4()
        contract = Contract(
            id=contract_id,
            deal_id=deal_id,
            proposal_id=proposal_id,
            owner_user_id=owner_user_id,
            status=ContractStatus.DRAFT,
            title=title,
            content=content,
            client_snapshot=client_snapshot,
            ai_generated=ai_generated,
            signed_at=None,
            completed_at=None,
            terminated_at=None,
            termination_reason=None,
            share_token=None,
            share_token_expires_at=None,
            created_at=now,
            updated_at=now,
        )
        initial_version = ContractVersion(
            id=uuid.uuid4(),
            contract_id=contract_id,
            version=1,
            content=content,
            created_by=owner_user_id,
            created_at=now,
            change_summary="Initial version",
        )
        agg = cls(contract=contract, versions=[initial_version])
        agg._pending_events.append(
            ContractCreatedEvent(
                event_id=uuid.uuid4(),
                aggregate_id=contract_id,
                occurred_at=now,
                deal_id=deal_id,
                proposal_id=proposal_id,
                owner_user_id=owner_user_id,
            )
        )
        return agg

    def send_for_signature(self) -> None:
        self.contract.send_for_signature()

    def sign(self) -> None:
        self.contract.sign()
        self._pending_events.append(
            ContractSignedEvent(
                event_id=uuid.uuid4(),
                aggregate_id=self.contract.id,
                occurred_at=self.contract.signed_at,  # type: ignore[arg-type]
                deal_id=self.contract.deal_id,
                owner_user_id=self.contract.owner_user_id,
            )
        )

    def add_milestone(
        self,
        title: str,
        amount: Money,
        description: str | None = None,
        due_date: datetime | None = None,
    ) -> PaymentMilestone:
        milestone = PaymentMilestone(
            id=uuid.uuid4(),
            contract_id=self.contract.id,
            title=title,
            description=description,
            amount=amount,
            due_date=due_date,
            completed_at=None,
        )
        self.milestones.append(milestone)
        return milestone

    def complete_milestone(self, milestone_id: uuid.UUID) -> PaymentMilestone:
        milestone = next((m for m in self.milestones if m.id == milestone_id), None)
        if milestone is None:
            raise ValueError(f"Milestone {milestone_id} not found on this contract")
        milestone.complete()
        self._pending_events.append(
            ContractMilestoneReachedEvent(
                event_id=uuid.uuid4(),
                aggregate_id=self.contract.id,
                occurred_at=milestone.completed_at,  # type: ignore[arg-type]
                milestone_id=milestone_id,
                deal_id=self.contract.deal_id,
                amount=milestone.amount,
            )
        )
        return milestone

    def complete(self) -> None:
        self.contract.complete()
        self._pending_events.append(
            ContractCompletedEvent(
                event_id=uuid.uuid4(),
                aggregate_id=self.contract.id,
                occurred_at=self.contract.completed_at,  # type: ignore[arg-type]
                deal_id=self.contract.deal_id,
            )
        )

    def terminate(self, reason: str | None = None) -> None:
        self.contract.terminate(reason)
        self._pending_events.append(
            ContractTerminatedEvent(
                event_id=uuid.uuid4(),
                aggregate_id=self.contract.id,
                occurred_at=self.contract.terminated_at,  # type: ignore[arg-type]
                deal_id=self.contract.deal_id,
                reason=reason,
            )
        )

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._pending_events)
        self._pending_events.clear()
        return events
