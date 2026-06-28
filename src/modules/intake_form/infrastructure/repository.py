import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import (
    IntakeFormConfigModel,
    IntakeFormFieldModel,
    UserModel,
)


@dataclass
class IntakeFormRepository:
    db: AsyncSession

    async def get_user_by_token(self, share_token: str):
        return await self.db.scalar(
            select(UserModel).where(
                UserModel.intake_share_token == share_token,
                UserModel.status == "active",
                UserModel.deleted_at.is_(None),
            )
        )

    async def get_user(self, user_id: uuid.UUID):
        return await self.db.scalar(
            select(UserModel).where(UserModel.id == user_id, UserModel.deleted_at.is_(None))
        )

    async def get_by_owner(self, owner_user_id: uuid.UUID):
        return await self.db.scalar(
            select(IntakeFormConfigModel).where(
                IntakeFormConfigModel.owner_user_id == owner_user_id
            )
        )

    async def create_config(
        self, *, owner_user_id: uuid.UUID, title: str, description, is_active: bool
    ):
        config = IntakeFormConfigModel(
            owner_user_id=owner_user_id,
            title=title,
            description=description,
            is_active=is_active,
        )
        self.db.add(config)
        await self.db.flush()
        await self.db.refresh(config)
        return config

    async def update_config(
        self, config: IntakeFormConfigModel, *, title: str, description, is_active: bool
    ):
        config.title = title
        config.description = description
        config.is_active = is_active
        await self.db.flush()
        await self.db.refresh(config)
        return config

    async def get_fields(self, form_id: uuid.UUID) -> list[IntakeFormFieldModel]:
        result = await self.db.execute(
            select(IntakeFormFieldModel)
            .where(IntakeFormFieldModel.form_id == form_id)
            .order_by(IntakeFormFieldModel.sort_order)
        )
        return list(result.scalars().all())

    async def get_visible_fields(self, form_id: uuid.UUID) -> list[IntakeFormFieldModel]:
        result = await self.db.execute(
            select(IntakeFormFieldModel)
            .where(
                IntakeFormFieldModel.form_id == form_id, IntakeFormFieldModel.is_visible.is_(True)
            )
            .order_by(IntakeFormFieldModel.sort_order)
        )
        return list(result.scalars().all())

    async def delete_fields(self, form_id: uuid.UUID) -> None:
        await self.db.execute(
            delete(IntakeFormFieldModel).where(IntakeFormFieldModel.form_id == form_id)
        )

    async def create_field(
        self,
        *,
        form_id: uuid.UUID,
        field_key: str,
        label: str,
        placeholder,
        field_type: str,
        is_required: bool,
        is_visible: bool,
        sort_order: int,
    ):
        field = IntakeFormFieldModel(
            form_id=form_id,
            field_key=field_key,
            label=label,
            placeholder=placeholder,
            field_type=field_type,
            is_required=is_required,
            is_visible=is_visible,
            sort_order=sort_order,
        )
        self.db.add(field)
        await self.db.flush()
        return field
