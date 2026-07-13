import uuid

from pydantic import BaseModel, ConfigDict


class IntakeFormFieldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    field_key: str
    label: str
    placeholder: str | None
    field_type: str
    is_required: bool
    is_visible: bool
    sort_order: int


class IntakeFormResponse(BaseModel):
    id: uuid.UUID | None
    title: str
    description: str | None
    is_active: bool
    share_url: str | None
    fields: list[IntakeFormFieldResponse]


class PublicIntakeFormFieldResponse(BaseModel):
    field_key: str
    label: str
    placeholder: str | None
    field_type: str
    is_required: bool


class ProfessionFieldOptionResponse(BaseModel):
    field_key: str
    label: str
    field_type: str
    options: list[str] | None
    is_required: bool


class ProfessionOptionResponse(BaseModel):
    value: str
    label: str
    fields: list[ProfessionFieldOptionResponse]


class PublicIntakeFormConfigResponse(BaseModel):
    title: str
    description: str | None
    freelancer_name: str
    fields: list[PublicIntakeFormFieldResponse]
    professions: list[ProfessionOptionResponse]
