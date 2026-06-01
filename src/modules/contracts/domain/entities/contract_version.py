import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ContractVersion:
    """Immutable snapshot of contract content at a given version."""

    id: uuid.UUID
    contract_id: uuid.UUID
    version: int
    content: dict[str, object]
    created_by: uuid.UUID
    created_at: datetime
    change_summary: str | None
