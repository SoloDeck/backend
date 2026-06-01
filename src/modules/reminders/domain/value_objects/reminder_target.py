import uuid
from dataclasses import dataclass
from enum import Enum


class ReminderTargetType(str, Enum):
    DEAL = "deal"
    CLIENT = "client"
    INVOICE = "invoice"
    CONTRACT = "contract"


@dataclass(frozen=True)
class ReminderTarget:
    """Polymorphic reference to a business object.

    No database FK exists for target_id — integrity enforced at app layer.
    """
    target_type: ReminderTargetType
    target_id: uuid.UUID
