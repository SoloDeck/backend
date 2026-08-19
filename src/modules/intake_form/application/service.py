import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.modules.intake_form.infrastructure.repository import IntakeFormRepository
from src.modules.intake_form.schemas.request import IntakeFormUpdateRequest
from src.modules.intake_form.schemas.response import (
    IntakeFormFieldResponse,
    IntakeFormResponse,
    PublicIntakeFormConfigResponse,
    PublicIntakeFormFieldResponse,
    PublicProfileResponse,
)
from src.shared.exceptions.domain import NotFoundError, ValidationError

_DEFAULT_FIELDS = [
    {
        "field_key": "name",
        "label": "Họ tên khách hàng",
        "placeholder": "Nguyễn Văn A",
        "field_type": "text",
        "is_required": True,
        "is_visible": True,
        "sort_order": 1,
    },
    {
        "field_key": "phone",
        "label": "Số điện thoại",
        "placeholder": "09xx xxx xxx",
        "field_type": "phone",
        "is_required": True,
        "is_visible": True,
        "sort_order": 2,
    },
    {
        "field_key": "email",
        "label": "Email",
        "placeholder": "email@vidu.vn",
        "field_type": "email",
        "is_required": False,
        "is_visible": True,
        "sort_order": 3,
    },
    {
        "field_key": "project_name",
        "label": "Tên dự án",
        "placeholder": "Ví dụ: Thiết kế trang bán hàng",
        "field_type": "text",
        "is_required": True,
        "is_visible": True,
        "sort_order": 4,
    },
    {
        "field_key": "inquiry_text",
        "label": "Mô tả nhu cầu",
        "placeholder": "Mô tả chi tiết yêu cầu của bạn...",
        "field_type": "textarea",
        "is_required": True,
        "is_visible": True,
        "sort_order": 5,
    },
    {
        "field_key": "estimated_budget",
        "label": "Ngân sách dự kiến",
        "placeholder": "Ví dụ: 5 - 10 triệu",
        "field_type": "text",
        "is_required": False,
        "is_visible": True,
        "sort_order": 6,
    },
    {
        "field_key": "desired_timeline",
        "label": "Timeline mong muốn",
        "placeholder": "Ví dụ: 2 tuần",
        "field_type": "text",
        "is_required": False,
        "is_visible": True,
        "sort_order": 7,
    },
]


def _default_field_responses() -> list[IntakeFormFieldResponse]:
    return [IntakeFormFieldResponse(id=uuid.uuid4(), **f) for f in _DEFAULT_FIELDS]


@dataclass
class IntakeFormService:
    db: AsyncSession
    repo: IntakeFormRepository | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = IntakeFormRepository(self.db)

    async def get_form_config(self, owner_user_id: uuid.UUID) -> IntakeFormResponse:
        user = await self.repo.get_user(owner_user_id)
        share_url = None
        if user:
            # Miền lấy từ cấu hình, KHÔNG ghi cứng: chỗ này từng là "https://solodesk.vn"
            # trong khi nhóm chỉ sở hữu solodesk.space — link trả về trỏ vào miền của người
            # khác. Ưu tiên tên đường dẫn riêng nếu freelancer đã đặt; chưa đặt thì dùng
            # link token, vốn không dò được.  #Huynh
            base = settings.frontend_url.rstrip("/")
            if user.profile_slug:
                share_url = f"{base}/{user.profile_slug}"
            elif user.intake_share_token:
                share_url = f"{base}/ho-so/{user.intake_share_token}"

        config = await self.repo.get_by_owner(owner_user_id)
        if config is None:
            return IntakeFormResponse(
                id=None,
                title="Gửi yêu cầu dự án",
                description=None,
                is_active=True,
                share_url=share_url,
                fields=_default_field_responses(),
            )

        fields = await self.repo.get_fields(config.id)
        return IntakeFormResponse(
            id=config.id,
            title=config.title,
            description=config.description,
            is_active=config.is_active,
            share_url=share_url,
            fields=[IntakeFormFieldResponse.model_validate(f) for f in fields],
        )

    async def save_form_config(
        self, owner_user_id: uuid.UUID, payload: IntakeFormUpdateRequest
    ) -> IntakeFormResponse:
        config = await self.repo.get_by_owner(owner_user_id)
        if config is None:
            config = await self.repo.create_config(
                owner_user_id=owner_user_id,
                title=payload.title,
                description=payload.description,
                is_active=payload.is_active,
            )
        else:
            config = await self.repo.update_config(
                config,
                title=payload.title,
                description=payload.description,
                is_active=payload.is_active,
            )

        await self.repo.delete_fields(config.id)
        for f in payload.fields:
            await self.repo.create_field(form_id=config.id, **f.model_dump())

        return await self.get_form_config(owner_user_id)

    async def get_public_config(self, share_token: str) -> PublicIntakeFormConfigResponse:
        user = await self.repo.get_user_by_token(share_token)
        if user is None:
            raise NotFoundError("Intake form not found or link is invalid")

        config = await self.repo.get_by_owner(user.id)
        # KHÔNG rơi về email: `full_name` là NOT NULL nên nhánh đó chỉ kích hoạt khi tên
        # rỗng — tức là nó chỉ tồn tại để rò email chủ tài khoản ra trang ai cũng mở được.
        freelancer_name = user.full_name or "Freelancer"

        if config is None:
            fields = [
                PublicIntakeFormFieldResponse(
                    **{
                        k: v
                        for k, v in f.items()
                        if k in ("field_key", "label", "placeholder", "field_type", "is_required")
                    }
                )
                for f in _DEFAULT_FIELDS
                if f["is_visible"]
            ]
            return PublicIntakeFormConfigResponse(
                title="Gửi yêu cầu dự án",
                description=None,
                freelancer_name=freelancer_name,
                fields=fields,
                is_active=True,
            )

        db_fields = await self.repo.get_visible_fields(config.id)
        return PublicIntakeFormConfigResponse(
            title=config.title,
            description=config.description,
            freelancer_name=freelancer_name,
            is_active=config.is_active,
            fields=[
                PublicIntakeFormFieldResponse(
                    field_key=f.field_key,
                    label=f.label,
                    placeholder=f.placeholder,
                    field_type=f.field_type,
                    is_required=f.is_required,
                )
                for f in db_fields
            ],
        )

    async def get_public_profile(self, share_token: str) -> PublicProfileResponse:
        """Hồ sơ freelancer cho trang chia sẻ, tra bằng share_token.

        KHÔNG lọc theo cờ "hiện công khai" như danh bạ cũ làm: chính freelancer là người
        phát tán link này, gửi link ra tức là đã đồng ý cho xem. Còn ai không phát link thì
        trang của họ không tồn tại với thế giới bên ngoài — không có chỗ nào liệt kê ra.

        Câu lỗi dùng CHUNG cho token sai lẫn token không tồn tại: phân biệt hai trường hợp
        là biến endpoint thành máy dò xem token nào có thật.  #Huynh
        """
        user = await self.repo.get_user_by_token(share_token)
        if user is None:
            raise NotFoundError("Profile not found or link is invalid")

        return PublicProfileResponse(
            full_name=user.full_name or "Freelancer",
            professional_title=user.professional_title,
            bio=user.bio,
            avatar_url=user.avatar_url,
            cover_url=user.cover_url,
            brand_color=user.brand_color,
            skills=user.skills or [],
            portfolio_url=user.portfolio_url,
        )

    async def validate_submission(self, share_token: str, payload) -> None:
        """Validate that all required fields (per form config) are present in the payload."""
        user = await self.repo.get_user_by_token(share_token)
        if user is None:
            raise NotFoundError("Intake form not found or link is invalid")

        config = await self.repo.get_by_owner(user.id)
        if config is None:
            required_keys = {"name", "inquiry_text"}
        else:
            # Công tắc "Biểu mẫu đang hoạt động" phải chặn được THẬT. Trước đây `is_active`
            # đi vòng qua PUT /intake-form rồi nằm im — không hàm nào phía công khai đọc nó,
            # nên freelancer tắt đi mà khách vẫn gửi được như thường, trái hẳn dòng mô tả
            # ngay dưới công tắc. Chặn ở đây chứ không chỉ ẩn form trên giao diện: ai gọi
            # thẳng API vẫn phải bị từ chối.  #Huynh
            if not config.is_active:
                raise ValidationError(
                    "Freelancer hiện không nhận yêu cầu mới qua biểu mẫu này."
                )
            fields = await self.repo.get_visible_fields(config.id)
            required_keys = {f.field_key for f in fields if f.is_required}

        payload_values = {
            "name": getattr(payload, "name", None),
            "phone": getattr(payload, "phone", None),
            "email": getattr(payload, "email", None),
            "project_name": getattr(payload, "project_name", None),
            "inquiry_text": getattr(payload, "inquiry_text", None),
            "estimated_budget": getattr(payload, "estimated_budget", None),
            "desired_timeline": getattr(payload, "desired_timeline", None),
        }
        missing = [k for k in required_keys if not payload_values.get(k)]
        if missing:
            raise ValidationError(f"Required fields missing: {', '.join(sorted(missing))}")
