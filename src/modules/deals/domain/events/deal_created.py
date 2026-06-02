import uuid
from dataclasses import dataclass
from datetime import datetime

from src.shared.domain.base import DomainEvent
from src.modules.deals.domain.value_objects.deal_stage import DealStage


@dataclass(frozen=True)
class DealCreatedEvent(DomainEvent):
    owner_user_id: uuid.UUID
    client_id: uuid.UUID
    title: str
    initial_stage: DealStage
