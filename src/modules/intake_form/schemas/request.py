from pydantic import BaseModel, Field


class IntakeFormFieldRequest(BaseModel):
    field_key: str = Field(max_length=100)
    label: str = Field(max_length=200)
    placeholder: str | None = Field(default=None, max_length=500)
    field_type: str = Field(default="text", max_length=50)
    is_required: bool = False
    is_visible: bool = True
    sort_order: int = 0


class IntakeFormUpdateRequest(BaseModel):
    title: str = Field(max_length=500)
    description: str | None = None
    is_active: bool = True
    fields: list[IntakeFormFieldRequest]
