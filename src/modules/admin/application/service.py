"""Admin application service."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.shared.constants import (
    SUPPORTED_LLM_MODELS,
    SUPPORTED_LLM_PROVIDERS,
)
from src.ai.shared.llm_provider import get_llm_provider
from src.config.settings import settings
from src.infrastructure.database.models import AIProviderConfigurationModel, PlanModel, SubscriptionModel, UserModel
from src.modules.admin.domain.entities import AdminUser, FeatureFlagRollout, SubscriptionOverride
from src.modules.admin.infrastructure.repository import AdminRepository
from src.modules.admin.schemas.request import (
    AdminCreateTemplateRequest,
    AdminPlanRequest,
    AdminSubscriptionOverrideRequest,
    AdminUpdateFeatureFlagRequest,
    AdminUpdatePlanRequest,
    AdminUpdateTemplateRequest,
    AdminUpdateUserRequest,
)
from src.shared.exceptions.domain import (
    AlreadyExistsError,
    BusinessRuleError,
    NotFoundError,
    ValidationError,
)


# Gói miễn phí là gói HỆ THỐNG, không phải một mặt hàng trong bảng giá: người đăng ký mới
# được gán vào nó (`auth`), và job hết hạn hạ mọi gói trả phí về nó (`subscriptions`). Cả
# hai chỗ đều tra theo MÃ này. Mất nó, hoặc đổi mã nó, là gãy cả hai luồng — im lặng, vì
# cả hai đều `if free_plan is None` rồi bỏ qua.  #Huynh
_SYSTEM_PLAN_SLUG = "free"


def _vnd(amount: Decimal | int) -> str:
    """``50000000`` → ``"50.000.000"``.

    Cố ý nhân đôi một dòng với `integrations/momo/client.py` thay vì dựng một module tiền
    tệ dùng chung: chỉ hai nơi cần, và để `modules/admin` import `integrations/momo` chỉ
    vì một hàm định dạng là một ràng buộc đắt hơn thứ nó tiết kiệm.
    """
    return f"{int(amount):,}".replace(",", ".")


@dataclass
class AdminService:
    db: AsyncSession
    repo: AdminRepository | None = None

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = AdminRepository(self.db)

    # -------------------------------------------------------------------------
    # Users
    # -------------------------------------------------------------------------

    async def list_users(self) -> list:
        return await self.repo.list_users()

    async def list_users_paginated(
        self,
        *,
        status: str | None = None,
        role: str | None = None,
        search: str | None = None,
        plan_slug: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list, int]:
        return await self.repo.list_users_paginated(
            status=status,
            role=role,
            search=search,
            plan_slug=plan_slug,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )

    async def get_user(self, user_id: uuid.UUID) -> UserModel:
        user = await self.repo.get_user(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found")
        return user

    async def update_user(
        self, user_id: uuid.UUID, payload: AdminUpdateUserRequest, *, admin_id: uuid.UUID
    ) -> UserModel:
        user = await self.get_user(user_id)
        changes: list[str] = []
        if payload.role is not None:
            user.role = payload.role
            changes.append(f"role={payload.role}")
        if payload.status is not None:
            user.status = payload.status
            changes.append(f"status={payload.status}")
        if payload.full_name is not None:
            user.full_name = payload.full_name
            changes.append(f"full_name={payload.full_name}")
        if payload.email is not None:
            existing = await self.repo.get_user_by_email(payload.email, exclude_user_id=user_id)
            if existing is not None:
                raise AlreadyExistsError(f"Email '{payload.email}' is already in use")
            user.email = payload.email
            changes.append(f"email={payload.email}")
        if payload.phone is not None:
            existing = await self.repo.get_user_by_phone(payload.phone, exclude_user_id=user_id)
            if existing is not None:
                raise AlreadyExistsError(f"Phone '{payload.phone}' is already in use")
            user.phone = payload.phone
            changes.append(f"phone={payload.phone}")

        user = await self.repo.save(user)
        if changes:
            await self.repo.create_audit_log(
                event_type="user.updated",
                actor_user_id=admin_id,
                target_type="user",
                target_id=user_id,
                description=f"Admin updated user {user.email}: {', '.join(changes)}",
            )
        return user

    async def suspend_user(
        self, user_id: uuid.UUID, *, admin_id: uuid.UUID
    ) -> UserModel:
        user = await self.get_user(user_id)
        is_last_active_admin = False
        if user.role == "admin":
            active_admin_count = await self.repo.count_active_admins()
            is_last_active_admin = active_admin_count <= 1

        entity = AdminUser(id=user.id, email=user.email, role=user.role, status=user.status)
        entity.suspend(is_last_active_admin=is_last_active_admin)
        user.status = entity.status
        user.sessions_revoked_at = datetime.now(UTC)

        user = await self.repo.save(user)
        await self.repo.create_audit_log(
            event_type="user.suspended",
            actor_user_id=admin_id,
            target_type="user",
            target_id=user_id,
            description=f"Admin suspended user {user.email}",
        )
        return user

    async def reinstate_user(
        self, user_id: uuid.UUID, *, admin_id: uuid.UUID
    ) -> UserModel:
        user = await self.get_user(user_id)
        entity = AdminUser(id=user.id, email=user.email, role=user.role, status=user.status)
        entity.reinstate()
        user.status = entity.status

        user = await self.repo.save(user)
        await self.repo.create_audit_log(
            event_type="user.reinstated",
            actor_user_id=admin_id,
            target_type="user",
            target_id=user_id,
            description=f"Admin reinstated user {user.email}",
        )
        return user

    async def revoke_user_sessions(self, user_id: uuid.UUID, *, admin_id: uuid.UUID) -> None:
        user = await self.get_user(user_id)
        user.sessions_revoked_at = datetime.now(UTC)

        user = await self.repo.save(user)
        await self.repo.create_audit_log(
            event_type="user.sessions_revoked",
            actor_user_id=admin_id,
            target_type="user",
            target_id=user_id,
            description=f"Admin revoked all sessions for user {user.email}",
        )

    # -------------------------------------------------------------------------
    # Plans
    # -------------------------------------------------------------------------

    async def list_plans(self) -> list:
        return await self.repo.list_plans()

    async def get_plan(self, plan_id: uuid.UUID):
        plan = await self.repo.get_plan(plan_id)
        if plan is None:
            raise NotFoundError(f"Plan {plan_id} not found")
        return plan

    @staticmethod
    def _assert_price_is_payable(price: Decimal) -> None:
        """Gói phải hoặc miễn phí, hoặc có giá mà cổng thanh toán nhận được.

        0đ = gói miễn phí, KHÔNG đi qua cổng thanh toán nên không bị ràng buộc gì. Còn
        lại thì phải nằm trong hạn mức MoMo, nếu không admin vừa tạo ra một gói BÀY RA
        ĐỂ BÁN NHƯNG KHÔNG MUA ĐƯỢC: người dùng bấm "Nâng cấp qua MoMo" và chắc chắn ăn
        lỗi, lần nào cũng vậy — trong khi chỗ hỏng thật nằm ở màn hình quản trị từ tuần
        trước.

        Chặn ở đây, chỗ DUY NHẤT giá gói được ghi vào DB, rẻ hơn nhiều so với để phát
        hiện lúc người dùng đang cầm ví.  #Huynh
        """
        if price == 0:
            return
        if not settings.momo_min_amount <= price <= settings.momo_max_amount:
            raise ValidationError(
                f"Giá gói phải là 0đ (gói miễn phí) hoặc nằm trong khoảng "
                f"{_vnd(settings.momo_min_amount)}đ – {_vnd(settings.momo_max_amount)}đ "
                f"— đây là hạn mức MoMo nhận cho một giao dịch. Giá vừa nhập: "
                f"{_vnd(price)}đ."
            )

    @staticmethod
    def _assert_not_system_plan(plan, *, action: str) -> None:
        """Gói Free không được xoá, không được ngừng bán, không được đổi mã."""
        if plan.slug != _SYSTEM_PLAN_SLUG:
            return
        raise BusinessRuleError(
            f"Không {action} được gói Free. Đây là gói gán cho mọi người đăng ký mới và "
            f"là đích hạ gói khi một gói trả phí hết hạn — mất nó là gãy cả hai luồng, "
            f"mà không có lỗi nào hiện ra."
        )

    async def create_plan(self, payload: AdminPlanRequest, *, admin_id: uuid.UUID | None = None):
        self._assert_price_is_payable(payload.price_monthly)
        if await self.repo.get_plan_by_name(payload.name) is not None:
            raise AlreadyExistsError(f"Plan name '{payload.name}' is already in use")
        if await self.repo.get_plan_by_slug(payload.slug) is not None:
            raise AlreadyExistsError(f"Plan slug '{payload.slug}' is already in use")
        plan = await self.repo.create_plan(
            name=payload.name,
            slug=payload.slug,
            price_monthly=payload.price_monthly,
            currency=payload.currency,
            can_use_ai=payload.can_use_ai,
            can_export_pdf=payload.can_export_pdf,
            max_clients=payload.max_clients,
            max_deals=payload.max_deals,
            max_ai_generations_per_month=payload.max_ai_generations_per_month,
        )
        await self.repo.create_audit_log(
            event_type="plan.created",
            actor_user_id=admin_id,
            target_type="plan",
            target_id=plan.id,
            description=f"Admin tạo gói '{plan.name}' ({plan.slug})",
        )
        return plan

    async def update_plan(
        self,
        plan_id: uuid.UUID,
        payload: AdminUpdatePlanRequest,
        *,
        admin_id: uuid.UUID | None = None,
    ):
        plan = await self.repo.get_plan(plan_id)
        if plan is None:
            raise NotFoundError(f"Plan {plan_id} not found")

        fields = payload.model_fields_set
        # Chỉ soi giá khi payload THẬT SỰ đụng tới giá. Gói cũ trong DB có thể đang để
        # một mức giá không còn hợp lệ; chặn cả những lần sửa không liên quan (đổi tên,
        # tắt gói) là khoá luôn đường duy nhất để đi sửa nó.  #Huynh
        # `is not None` chứ không chỉ kiểm tra có mặt: kiểu là `PlanPrice | None`, nên
        # `{"price_monthly": null}` vẫn nằm trong `model_fields_set`. So `None` với số sẽ
        # ném TypeError và biến một payload sai thành 500 trần.
        if "price_monthly" in fields and payload.price_monthly is not None:
            self._assert_price_is_payable(payload.price_monthly)
        # Gói Free vẫn đổi tên / đổi quyền lợi được — chỉ hai thứ khiến code không tìm
        # thấy nó nữa là bị cấm: tắt nó đi, và đổi mã của nó.
        if "is_active" in fields and payload.is_active is False:
            self._assert_not_system_plan(plan, action="ngừng bán")
        if "slug" in fields and payload.slug != plan.slug:
            self._assert_not_system_plan(plan, action="đổi mã")
        if "name" in fields and payload.name != plan.name:
            if await self.repo.get_plan_by_name(payload.name, exclude_plan_id=plan_id) is not None:
                raise AlreadyExistsError(f"Plan name '{payload.name}' is already in use")
        if "slug" in fields and payload.slug != plan.slug:
            if await self.repo.get_plan_by_slug(payload.slug, exclude_plan_id=plan_id) is not None:
                raise AlreadyExistsError(f"Plan slug '{payload.slug}' is already in use")

        for field in fields:
            setattr(plan, field, getattr(payload, field))
        plan = await self.repo.save(plan)

        await self.repo.create_audit_log(
            event_type="plan.updated",
            actor_user_id=admin_id,
            target_type="plan",
            target_id=plan_id,
            description=f"Admin sửa gói '{plan.name}': {', '.join(sorted(fields))}",
        )
        return plan

    async def delete_plan(self, plan_id: uuid.UUID, *, admin_id: uuid.UUID | None = None) -> None:
        """Xoá HẲN một gói — chỉ dành cho gói chưa từng được dùng.

        Một gói là hai thứ khác nhau cùng lúc: một mặt hàng đang bày bán, và một sự thật
        lịch sử gắn vào hoá đơn ("tháng 7 người này trả 199.000đ cho gói Pro"). Bỏ mặt
        hàng khỏi quầy thì lúc nào cũng được; xoá sự thật lịch sử thì không bao giờ.

        Nên xoá thật CHỈ hợp lệ khi không có sự thật nào để xoá — chưa ai đăng ký và chưa
        có giao dịch nào. Đó đúng là ca "lỡ tay tạo nhầm", cũng là ca duy nhất admin thật
        sự cần xoá. Gói đã có người dùng thì đường đúng là `is_active = false`: nó biến
        khỏi bảng giá, không ai mua mới được, còn người đang dùng giữ nguyên quyền lợi
        tới hết kỳ đã trả tiền rồi mới bị hạ về Free.

        Đây cũng là cách Stripe/Paddle làm: một mức giá đã từng dùng thì không xoá được,
        chỉ lưu trữ.  #Huynh
        """
        plan = await self.repo.get_plan(plan_id)
        if plan is None:
            raise NotFoundError(f"Plan {plan_id} not found")

        self._assert_not_system_plan(plan, action="xoá")

        subscribers, payments = await self.repo.count_plan_usage(plan_id)
        if subscribers or payments:
            raise BusinessRuleError(
                f"Không xoá được gói '{plan.name}' vì đã có người dùng "
                f"({subscribers} lượt đăng ký, {payments} giao dịch). Xoá là hoá đơn cũ "
                f"mất chỗ trỏ về. Hãy NGỪNG BÁN gói này: nó sẽ biến khỏi bảng giá và "
                f"không ai mua mới được, còn người đang dùng vẫn giữ quyền lợi tới hết kỳ."
            )

        # Ghi nhật ký TRƯỚC khi xoá. `target_id` cố ý không có khoá ngoại (xem models.py),
        # nên bản ghi này sống sót sau khi gói biến mất — đó là toàn bộ điểm của nó.
        await self.repo.create_audit_log(
            event_type="plan.deleted",
            actor_user_id=admin_id,
            target_type="plan",
            target_id=plan.id,
            description=f"Admin xoá gói '{plan.name}' ({plan.slug})",
        )
        await self.repo.delete_plan(plan)

    # -------------------------------------------------------------------------
    # Subscriptions
    # -------------------------------------------------------------------------

    async def list_subscriptions_paginated(
        self,
        *,
        status: str | None = None,
        plan_slug: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[tuple], int]:
        return await self.repo.list_subscriptions_paginated(
            status=status,
            plan_slug=plan_slug,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )

    async def override_subscription(
        self,
        subscription_id: uuid.UUID,
        payload: AdminSubscriptionOverrideRequest,
        admin_id: uuid.UUID,
    ) -> tuple[SubscriptionModel, PlanModel]:
        sub = await self.repo.get_subscription(subscription_id)
        if sub is None:
            raise NotFoundError(f"Subscription {subscription_id} not found")

        override = SubscriptionOverride(
            subscription_id=sub.id,
            plan_id=payload.plan_id if payload.plan_id is not None else sub.plan_id,
            override_by_admin_id=admin_id,
            override_expires_at=payload.override_expires_at,
        )  # __post_init__ raises OverrideExpiryInPastError for an expiry already in the past

        if payload.plan_id is not None:
            sub.plan_id = override.plan_id
        if payload.override_expires_at is not None:
            sub.override_expires_at = override.override_expires_at
        sub.override_by_admin_id = override.override_by_admin_id

        sub = await self.repo.save(sub)
        plan = await self.repo.get_plan(sub.plan_id)

        # Freelancer KHÔNG tự nâng cấp gói được (tự nâng cấp đòi cổng thanh toán thật).
        # Admin thu tiền ngoài hệ thống rồi kích hoạt tay. Mô hình đó chỉ đứng vững nếu
        # MỌI lần kích hoạt đều để lại dấu vết: ai làm, cho ai, lúc nào. Không có nhật ký
        # thì "admin kích hoạt thủ công" chỉ là một cái cửa sau.  #Huynh
        await self.repo.create_audit_log(
            event_type="subscription.overridden",
            actor_user_id=admin_id,
            target_type="subscription",
            target_id=subscription_id,
            description=(
                f"Admin đổi gói của user {sub.user_id} sang "
                f"'{plan.name if plan else sub.plan_id}'"
            ),
        )
        if plan is None:
            raise NotFoundError(f"Plan {sub.plan_id} not found")
        return sub, plan

    # -------------------------------------------------------------------------
    # Audit Logs
    # -------------------------------------------------------------------------

    async def list_audit_logs_paginated(
        self,
        *,
        event_type: str | None = None,
        target_type: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        sort_by: str = "occurred_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list, int]:
        return await self.repo.list_audit_logs_paginated(
            event_type=event_type,
            target_type=target_type,
            from_date=from_date,
            to_date=to_date,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )

    # -------------------------------------------------------------------------
    # Subscription Payments
    # -------------------------------------------------------------------------

    async def list_payments_paginated(
        self,
        *,
        status: str | None = None,
        provider: str | None = None,
        search: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list, int]:
        return await self.repo.list_payments_paginated(
            status=status,
            provider=provider,
            search=search,
            from_date=from_date,
            to_date=to_date,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )

    # -------------------------------------------------------------------------
    # AI Costs
    # -------------------------------------------------------------------------

    async def list_ai_costs_paginated(
        self,
        *,
        ai_module: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        sort_by: str = "occurred_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list, int]:
        return await self.repo.list_ai_costs_paginated(
            ai_module=ai_module,
            from_date=from_date,
            to_date=to_date,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )

    async def get_ai_cost_totals(
        self,
        *,
        ai_module: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> dict:
        return await self.repo.get_ai_cost_totals(
            ai_module=ai_module,
            from_date=from_date,
            to_date=to_date,
        )

    # -------------------------------------------------------------------------
    # AI Provider Configuration
    # -------------------------------------------------------------------------

    async def get_ai_provider_configuration(
            self,
    ) -> AIProviderConfigurationModel:

        configuration = await self.repo.get_ai_provider_configuration()

        if configuration is None:
            raise NotFoundError(
                "AI provider configuration not found"
            )

        return configuration

    async def update_ai_provider_configuration(
            self,
            *,
            llm_provider: str,
            llm_model: str,
            admin_id: uuid.UUID,
    ) -> AIProviderConfigurationModel:

        configuration = await self.get_ai_provider_configuration()

        # Normalize input
        llm_provider = llm_provider.strip().lower()
        llm_model = llm_model.strip()

        # Validate provider
        if llm_provider not in SUPPORTED_LLM_PROVIDERS:
            raise ValidationError(
                f"Unsupported LLM provider: {llm_provider}"
            )

        # Validate model belongs to provider
        supported_models = SUPPORTED_LLM_MODELS.get(
            llm_provider,
        )

        if supported_models is None:
            raise ValidationError(
                f"No models configured for provider: {llm_provider}"
            )

        if llm_model not in supported_models:
            raise ValidationError(
                f"Unsupported model '{llm_model}' "
                f"for provider '{llm_provider}'"
            )

        # Dựng thử provider TRƯỚC khi ghi. Tên hợp lệ không có nghĩa là dùng
        # được: GroqProvider/GeminiProvider ném RuntimeError khi thiếu API key,
        # và một provider chưa cài đặt `generate` thì ném TypeError. Nếu ghi
        # trước rồi mới phát hiện, PATCH vẫn trả 200 nhưng MỌI request AI sau đó
        # trả 500 (ProviderFactory đọc lại dòng này ở mọi request) cho tới khi
        # có người đổi ngược lại — mất toàn bộ tính năng AI vì một thao tác
        # tưởng như đã thành công.
        try:
            get_llm_provider(llm_provider, llm_model)
        except Exception as err:  # noqa: BLE001 — mọi lỗi khởi tạo đều KHÔNG được ghi
            raise ValidationError(
                f"LLM provider '{llm_provider}/{llm_model}' is not usable: {err}"
            ) from err

        # Update configuration
        configuration.llm_provider = llm_provider
        configuration.llm_model = llm_model
        configuration.updated_by = admin_id

        configuration = await (
            self.repo.update_ai_provider_configuration(
                configuration
            )
        )

        # Audit log
        await self.repo.create_audit_log(
            event_type="ai_provider.updated",
            actor_user_id=admin_id,
            target_type="ai_provider_configuration",
            target_id=configuration.id,
            description=(
                f"Admin changed AI configuration to "
                f"'{llm_provider}/{llm_model}'"
            ),
        )

        return configuration

    # -------------------------------------------------------------------------
    # Templates
    # -------------------------------------------------------------------------

    async def list_templates(
        self,
        *,
        template_type: str | None = None,
        profession: str | None = None,
        is_active: bool | None = None,
    ) -> list:
        return await self.repo.list_templates(
            template_type=template_type,
            profession=profession,
            is_active=is_active,
        )

    async def create_template(
        self,
        payload: AdminCreateTemplateRequest,
        *,
        admin_id: uuid.UUID,
    ):
        return await self.repo.create_template(
            name=payload.name,
            template_type=payload.template_type,
            profession=self._clean_profession(payload.profession),
            content=payload.content,
            plan_tier_required=payload.plan_tier_required,
            is_active=payload.is_active,
            created_by_admin_id=admin_id,
        )

    async def update_template(
        self,
        template_id: uuid.UUID,
        payload: AdminUpdateTemplateRequest,
    ):
        template = await self.repo.get_template(template_id)
        if template is None:
            raise NotFoundError(f"Template {template_id} not found")
        if payload.name is not None:
            template.name = payload.name
        # `in model_fields_set` chứ không phải `is not None`: với trường nullable, hai chuyện
        # "không gửi lên" và "gửi lên đúng null" khác hẳn nhau, mà `is not None` gộp chúng làm
        # một. Hệ quả: admin mở mẫu đang gắn nghề, chọn "Dùng chung cho mọi nghề", bấm Lưu, nhận
        # toast "Đã cập nhật mẫu." — nhưng cột giữ nguyên nghề cũ, và freelancer nghề khác vẫn
        # không thấy mẫu đó. Mở lại form thì select hiện đúng nghề cũ, không dấu vết gì.  #Huynh
        if "profession" in payload.model_fields_set:
            template.profession = self._clean_profession(payload.profession)
        if payload.content is not None:
            template.content = payload.content
            template.version_number = (template.version_number or 1) + 1
        if payload.is_active is not None:
            template.is_active = payload.is_active
        if payload.plan_tier_required is not None:
            template.plan_tier_required = payload.plan_tier_required
        return await self.repo.save(template)

    async def delete_template(
        self, template_id: uuid.UUID, *, admin_id: uuid.UUID | None = None
    ) -> None:
        """Xoá hẳn một mẫu hệ thống khỏi thư viện.

        An toàn với đề xuất/hợp đồng đã tạo: lúc sinh tài liệu, nội dung mẫu được COPY vào
        `proposals.content` / `contracts.content`, không có cột nào trỏ ngược về bảng mẫu.
        Ràng buộc duy nhất là `system_templates.parent_template_id` (mẫu con phái sinh) —
        còn mẫu con thì chặn, vì xoá cha sẽ vỡ khoá ngoại.  #Huynh
        """
        template = await self.repo.get_template(template_id)
        if template is None:
            raise NotFoundError(f"Template {template_id} not found")

        child_count = await self.repo.count_child_templates(template_id)
        if child_count:
            raise BusinessRuleError(
                f"Không xoá được mẫu '{template.name}': còn {child_count} mẫu phái sinh từ nó. "
                "Hãy xoá các mẫu con trước, hoặc đặt is_active=false để ẩn mẫu này."
            )

        # Ghi nhật ký TRƯỚC khi xoá, cùng lối với `delete_plan`: `target_id` cố ý không có
        # khoá ngoại (xem models.py) nên bản ghi sống sót sau khi mẫu biến mất, và đọc
        # thuộc tính trước `delete()` + `flush()` thì khỏi chạm vào instance đã tách phiên.
        await self.repo.create_audit_log(
            event_type="template.deleted",
            actor_user_id=admin_id,
            target_type="template",
            target_id=template.id,
            description=f"Admin xoá mẫu '{template.name}'",
        )
        await self.repo.delete_template(template)

    @staticmethod
    def _clean_profession(profession: str | None) -> str | None:
        """Chuẩn hoá + kiểm nghề qua SEAM, trả về giá trị để lưu.

        Chuỗi rỗng "" nghĩa là "mẫu dùng chung" → quy về None để cột lưu NULL, thay vì một
        slug rỗng vô nghĩa. Kiểm qua `is_valid_profession` (seam professions) chứ không đọc
        thẳng dict — sau này nghề chuyển sang bảng DB thì chỗ này không phải sửa.  #Huynh
        """
        from src.modules.intake_form.professions import is_valid_profession

        value = (profession or "").strip() or None
        if not is_valid_profession(value):
            raise ValidationError(f"Nghề không hợp lệ: {profession!r}")
        return value

    # -------------------------------------------------------------------------
    # Feature Flags
    # -------------------------------------------------------------------------

    async def list_feature_flags(self) -> list:
        return await self.repo.list_feature_flags()

    async def update_feature_flag(
        self,
        flag_name: str,
        payload: AdminUpdateFeatureFlagRequest,
    ):
        flag = await self.repo.get_feature_flag_by_name(flag_name)
        if flag is None:
            raise NotFoundError(f"Feature flag '{flag_name}' not found")

        entity = FeatureFlagRollout(
            flag_name=flag.flag_name,
            is_enabled=payload.is_enabled if payload.is_enabled is not None else flag.is_enabled,
            rollout_percentage=(
                payload.rollout_percentage
                if payload.rollout_percentage is not None
                else flag.rollout_percentage
            ),
            target_user_ids=(
                payload.target_user_ids
                if payload.target_user_ids is not None
                else flag.target_user_ids
            ),
        )  # __post_init__ raises InvalidRolloutPercentageError if out of [0, 100]

        flag.is_enabled = entity.is_enabled
        flag.rollout_percentage = entity.rollout_percentage
        flag.target_user_ids = entity.target_user_ids
        if payload.description is not None:
            flag.description = payload.description
        return await self.repo.save(flag)

    # -------------------------------------------------------------------------
    # Platform Metrics
    # -------------------------------------------------------------------------

    async def get_platform_metrics(self) -> dict:
        return await self.repo.get_platform_metrics()
