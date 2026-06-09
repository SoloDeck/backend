import uuid
from dataclasses import dataclass

from src.modules.deals.domain.value_objects.deal_stage import DealStage
from src.shared.domain.base import DomainEvent


@dataclass(frozen=True)
class DealStageChangedEvent(DomainEvent):
    old_stage: DealStage
    new_stage: DealStage
    actor_user_id: uuid.UUID
