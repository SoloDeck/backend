import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, or_, select
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
        """Tra freelancer bằng token chia sẻ HOẶC tên đường dẫn riêng.

        Một truy vấn cho cả hai là an toàn vì hai không gian giá trị không giao nhau: token
        do `secrets.token_urlsafe` sinh ra dài 43+ ký tự, còn slug bị chặn tối đa 32. Nhờ
        vậy endpoint công khai nhận được slug mà không phải thêm endpoint hay tham số nào.

        Vị từ này chỉ phục vụ `/profile` và `/config`. Đường GỬI form (`POST /intake/{v}`)
        và đính kèm đi qua `DealsRepository.get_owner_by_public_link` — cùng vị từ, chép
        sang vì AGENTS.md cấm gọi chéo repository giữa hai module. Sửa chỗ này thì phải
        sửa cả chỗ kia; test khoá: `test_slug_hoat_dong_tren_ca_ba_endpoint_cong_khai`.

        (Bản đầu của docstring này khẳng định cả ba endpoint dùng chung truy vấn ở đây —
        sai ngay lúc viết, và khách gửi form qua slug ăn 404 suốt vì thế.)  #Huynh
        """
        return await self.db.scalar(
            select(UserModel).where(
                or_(
                    UserModel.intake_share_token == share_token,
                    UserModel.profile_slug == share_token,
                ),
                UserModel.status == "active",
                UserModel.deleted_at.is_(None),
            )
        )

    async def list_public_profile_slugs(self) -> list[tuple[str, datetime]]:
        """Mọi hồ sơ có tên đường dẫn riêng, kèm mốc sửa gần nhất — nguồn cho sitemap.xml.

        Chỉ liệt kê hồ sơ ĐÃ đặt slug: link token 43 ký tự cố ý không dò được, đưa nó vào
        sitemap là tự phá luôn tính chất đó. Đặt slug là hành động chủ động của freelancer,
        tức là đã muốn có địa chỉ công khai.
        """
        result = await self.db.execute(
            select(UserModel.profile_slug, UserModel.updated_at)
            .where(
                UserModel.profile_slug.is_not(None),
                UserModel.status == "active",
                UserModel.deleted_at.is_(None),
            )
            .order_by(UserModel.updated_at.desc())
        )
        return [(slug, updated_at) for slug, updated_at in result.all()]

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
