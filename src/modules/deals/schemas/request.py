import uuid
from decimal import Decimal

from pydantic import AliasChoices, BaseModel, Field


class DealRequest(BaseModel):
    client_id: uuid.UUID
    title: str
    stage: str = "new_lead"
    source: str | None = None
    estimated_value: Decimal | None = None
    actual_value: Decimal | None = None
    currency: str = "VND"
    notes: str | None = None


class DealStageRequest(BaseModel):
    target_stage: str = Field(validation_alias=AliasChoices("target_stage", "stage"))

    @property
    def stage(self) -> str:
        return self.target_stage
