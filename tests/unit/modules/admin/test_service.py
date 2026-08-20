import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.modules.admin.application.service import AdminService
from src.modules.admin.domain.exceptions import (
    InvalidRolloutPercentageError,
    LastAdminSuspensionError,
    OverrideExpiryInPastError,
)
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


@dataclass
class UserStub:
    id: uuid.UUID
    email: str = "user@example.com"
    role: str = "freelancer"
    status: str = "active"
    full_name: str = "Test User"
    phone: str | None = None
    deleted_at: datetime | None = None
    sessions_revoked_at: datetime | None = None


@dataclass
class PlanStub:
    id: uuid.UUID
    name: str = "Pro"
    slug: str = "pro"
    price_monthly: Decimal = Decimal("199000")
    currency: str = "VND"
    can_use_ai: bool = True
    can_export_pdf: bool = True
    max_clients: int | None = None
    max_deals: int | None = None
    max_ai_generations_per_month: int = 50
    is_active: bool = True


@dataclass
class SubscriptionStub:
    id: uuid.UUID
    plan_id: uuid.UUID
    user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    override_expires_at: datetime | None = None
    override_by_admin_id: uuid.UUID | None = None


@dataclass
class TemplateStub:
    id: uuid.UUID
    name: str = "Default Proposal"
    template_type: str = "proposal"
    content: dict = field(default_factory=dict)
    plan_tier_required: str | None = None
    version_number: int = 1
    is_active: bool = False


@dataclass
class FeatureFlagStub:
    id: uuid.UUID
    flag_name: str = "new_dashboard"
    is_enabled: bool = False
    rollout_percentage: int = 0
    target_user_ids: list[uuid.UUID] | None = None
    description: str | None = None


def _repo(**overrides) -> AsyncMock:
    repo = AsyncMock()
    repo.save.side_effect = lambda obj: obj
    for key, value in overrides.items():
        getattr(repo, key).return_value = value
    return repo


# ---------------------------------------------------------------------------
# list_users / list_users_paginated
# ---------------------------------------------------------------------------


async def test_list_users_returns_repo_result() -> None:
    users = [UserStub(id=uuid.uuid4())]
    repo = _repo(list_users=users)
    service = AdminService(db=AsyncMock(), repo=repo)

    result = await service.list_users()

    assert result == users


async def test_list_users_paginated_passes_filters_through() -> None:
    repo = _repo(list_users_paginated=([], 0))
    service = AdminService(db=AsyncMock(), repo=repo)

    await service.list_users_paginated(status="active", role="admin", page=2, page_size=10)

    repo.list_users_paginated.assert_awaited_once_with(
        status="active",
        role="admin",
        search=None,
        plan_slug=None,
        sort_by="created_at",
        sort_order="desc",
        page=2,
        page_size=10,
    )


# ---------------------------------------------------------------------------
# get_user
# ---------------------------------------------------------------------------


class TestGetUser:
    async def test_success_returns_user(self) -> None:
        user = UserStub(id=uuid.uuid4())
        repo = _repo(get_user=user)
        service = AdminService(db=AsyncMock(), repo=repo)

        result = await service.get_user(user.id)

        assert result is user

    async def test_not_found_raises(self) -> None:
        repo = _repo(get_user=None)
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(NotFoundError):
            await service.get_user(uuid.uuid4())


# ---------------------------------------------------------------------------
# update_user
# ---------------------------------------------------------------------------


class TestUpdateUser:
    async def test_updates_fields_and_writes_audit_log(self) -> None:
        user = UserStub(id=uuid.uuid4())
        repo = _repo(get_user=user, get_user_by_email=None, get_user_by_phone=None)
        service = AdminService(db=AsyncMock(), repo=repo)

        result = await service.update_user(
            user.id,
            AdminUpdateUserRequest(role="admin", full_name="New Name"),
            admin_id=uuid.uuid4(),
        )

        assert result.role == "admin"
        assert result.full_name == "New Name"
        repo.create_audit_log.assert_awaited_once()

    async def test_no_changes_skips_audit_log(self) -> None:
        user = UserStub(id=uuid.uuid4())
        repo = _repo(get_user=user)
        service = AdminService(db=AsyncMock(), repo=repo)

        await service.update_user(user.id, AdminUpdateUserRequest(), admin_id=uuid.uuid4())

        repo.create_audit_log.assert_not_awaited()

    async def test_duplicate_email_raises(self) -> None:
        user = UserStub(id=uuid.uuid4())
        repo = _repo(get_user=user, get_user_by_email=UserStub(id=uuid.uuid4()))
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(AlreadyExistsError):
            await service.update_user(
                user.id,
                AdminUpdateUserRequest(email="taken@example.com"),
                admin_id=uuid.uuid4(),
            )

    async def test_duplicate_phone_raises(self) -> None:
        user = UserStub(id=uuid.uuid4())
        repo = _repo(get_user=user, get_user_by_phone=UserStub(id=uuid.uuid4()))
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(AlreadyExistsError):
            await service.update_user(
                user.id,
                AdminUpdateUserRequest(phone="0900000000"),
                admin_id=uuid.uuid4(),
            )

    async def test_user_not_found_raises(self) -> None:
        repo = _repo(get_user=None)
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(NotFoundError):
            await service.update_user(
                uuid.uuid4(), AdminUpdateUserRequest(full_name="X"), admin_id=uuid.uuid4()
            )


# ---------------------------------------------------------------------------
# suspend_user
# ---------------------------------------------------------------------------


class TestSuspendUser:
    async def test_suspends_freelancer(self) -> None:
        user = UserStub(id=uuid.uuid4(), role="freelancer", status="active")
        repo = _repo(get_user=user)
        service = AdminService(db=AsyncMock(), repo=repo)

        result = await service.suspend_user(user.id, admin_id=uuid.uuid4())

        assert result.status == "suspended"
        repo.create_audit_log.assert_awaited_once()

    async def test_suspends_admin_when_other_admins_remain(self) -> None:
        user = UserStub(id=uuid.uuid4(), role="admin", status="active")
        repo = _repo(get_user=user, count_active_admins=2)
        service = AdminService(db=AsyncMock(), repo=repo)

        result = await service.suspend_user(user.id, admin_id=uuid.uuid4())

        assert result.status == "suspended"

    async def test_blocks_suspending_last_admin(self) -> None:
        user = UserStub(id=uuid.uuid4(), role="admin", status="active")
        repo = _repo(get_user=user, count_active_admins=1)
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(LastAdminSuspensionError):
            await service.suspend_user(user.id, admin_id=uuid.uuid4())

        repo.save.assert_not_awaited()
        repo.create_audit_log.assert_not_awaited()

    async def test_user_not_found_raises(self) -> None:
        repo = _repo(get_user=None)
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(NotFoundError):
            await service.suspend_user(uuid.uuid4(), admin_id=uuid.uuid4())


# ---------------------------------------------------------------------------
# reinstate_user
# ---------------------------------------------------------------------------


class TestReinstateUser:
    async def test_reinstates_suspended_user(self) -> None:
        user = UserStub(id=uuid.uuid4(), status="suspended")
        repo = _repo(get_user=user)
        service = AdminService(db=AsyncMock(), repo=repo)

        result = await service.reinstate_user(user.id, admin_id=uuid.uuid4())

        assert result.status == "active"
        repo.create_audit_log.assert_awaited_once()


# ---------------------------------------------------------------------------
# revoke_user_sessions
# ---------------------------------------------------------------------------


class TestRevokeUserSessions:
    async def test_sets_sessions_revoked_at_and_logs_audit(self) -> None:
        user = UserStub(id=uuid.uuid4())
        repo = _repo(get_user=user)
        service = AdminService(db=AsyncMock(), repo=repo)

        before = datetime.now(UTC)
        await service.revoke_user_sessions(user.id, admin_id=uuid.uuid4())

        assert user.sessions_revoked_at is not None
        assert user.sessions_revoked_at >= before
        repo.create_audit_log.assert_awaited_once()

    async def test_nonexistent_user_raises_not_found(self) -> None:
        repo = _repo(get_user=None)
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(NotFoundError):
            await service.revoke_user_sessions(uuid.uuid4(), admin_id=uuid.uuid4())


# ---------------------------------------------------------------------------
# list_plans / get_plan
# ---------------------------------------------------------------------------


async def test_list_plans_returns_repo_result() -> None:
    plans = [PlanStub(id=uuid.uuid4())]
    repo = _repo(list_plans=plans)
    service = AdminService(db=AsyncMock(), repo=repo)

    assert await service.list_plans() == plans


class TestGetPlan:
    async def test_success(self) -> None:
        plan = PlanStub(id=uuid.uuid4())
        repo = _repo(get_plan=plan)
        service = AdminService(db=AsyncMock(), repo=repo)

        assert await service.get_plan(plan.id) is plan

    async def test_not_found_raises(self) -> None:
        repo = _repo(get_plan=None)
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(NotFoundError):
            await service.get_plan(uuid.uuid4())


# ---------------------------------------------------------------------------
# create_plan
# ---------------------------------------------------------------------------


def _plan_payload(**overrides) -> AdminPlanRequest:
    return AdminPlanRequest(
        **{
            "name": "Pro",
            "slug": "pro",
            "price_monthly": Decimal("199000"),
            "currency": "VND",
            **overrides,
        }
    )


class TestCreatePlan:
    async def test_success(self) -> None:
        created = PlanStub(id=uuid.uuid4())
        repo = _repo(get_plan_by_name=None, get_plan_by_slug=None, create_plan=created)
        service = AdminService(db=AsyncMock(), repo=repo)

        result = await service.create_plan(_plan_payload())

        assert result is created

    async def test_duplicate_name_raises(self) -> None:
        repo = _repo(get_plan_by_name=PlanStub(id=uuid.uuid4()))
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(AlreadyExistsError):
            await service.create_plan(_plan_payload())

    async def test_duplicate_slug_raises(self) -> None:
        repo = _repo(get_plan_by_name=None, get_plan_by_slug=PlanStub(id=uuid.uuid4()))
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(AlreadyExistsError):
            await service.create_plan(_plan_payload())


# ---------------------------------------------------------------------------
# update_plan
# ---------------------------------------------------------------------------


class TestUpdatePlan:
    async def test_success_updates_only_set_fields(self) -> None:
        plan = PlanStub(id=uuid.uuid4(), name="Pro", slug="pro")
        repo = _repo(get_plan=plan)
        service = AdminService(db=AsyncMock(), repo=repo)

        result = await service.update_plan(
            plan.id, AdminUpdatePlanRequest(price_monthly=Decimal("249000"))
        )

        assert result.price_monthly == Decimal("249000")
        assert result.name == "Pro"

    async def test_not_found_raises(self) -> None:
        repo = _repo(get_plan=None)
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(NotFoundError):
            await service.update_plan(uuid.uuid4(), AdminUpdatePlanRequest(name="X"))

    async def test_duplicate_name_raises(self) -> None:
        plan = PlanStub(id=uuid.uuid4(), name="Pro")
        repo = _repo(get_plan=plan, get_plan_by_name=PlanStub(id=uuid.uuid4()))
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(AlreadyExistsError):
            await service.update_plan(plan.id, AdminUpdatePlanRequest(name="Agency"))

    async def test_duplicate_slug_raises(self) -> None:
        plan = PlanStub(id=uuid.uuid4(), slug="pro")
        repo = _repo(get_plan=plan, get_plan_by_slug=PlanStub(id=uuid.uuid4()))
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(AlreadyExistsError):
            await service.update_plan(plan.id, AdminUpdatePlanRequest(slug="agency"))

    async def test_unchanged_name_does_not_trigger_duplicate_check(self) -> None:
        plan = PlanStub(id=uuid.uuid4(), name="Pro")
        repo = _repo(get_plan=plan)
        service = AdminService(db=AsyncMock(), repo=repo)

        await service.update_plan(plan.id, AdminUpdatePlanRequest(name="Pro"))

        repo.get_plan_by_name.assert_not_awaited()


# ---------------------------------------------------------------------------
# Hạn mức giá gói
#
# Một gói có phí nhưng để giá ngoài khoảng MoMo nhận là gói BÀY RA ĐỂ BÁN MÀ KHÔNG MUA
# ĐƯỢC: người dùng bấm "Nâng cấp qua MoMo" và chắc chắn ăn lỗi, lần nào cũng vậy. Chặn ở
# đây — chỗ duy nhất giá gói được ghi vào DB.
# ---------------------------------------------------------------------------


class TestPlanPriceGuard:
    async def test_create_rejects_price_below_momo_minimum(self) -> None:
        """200đ — đúng con số đã gây ra sự cố trên bản deploy."""
        repo = _repo(get_plan_by_name=None, get_plan_by_slug=None)
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(ValidationError) as excinfo:
            await service.create_plan(_plan_payload(price_monthly=Decimal("200")))

        assert "1.000" in excinfo.value.message

    async def test_create_rejects_price_above_momo_maximum(self) -> None:
        repo = _repo(get_plan_by_name=None, get_plan_by_slug=None)
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(ValidationError) as excinfo:
            await service.create_plan(_plan_payload(price_monthly=Decimal("50000001")))

        assert "50.000.000" in excinfo.value.message

    async def test_create_allows_zero_price_free_plan(self) -> None:
        """Gói miễn phí không đi qua cổng thanh toán nên không chịu hạn mức nào."""
        created = PlanStub(id=uuid.uuid4())
        repo = _repo(get_plan_by_name=None, get_plan_by_slug=None, create_plan=created)
        service = AdminService(db=AsyncMock(), repo=repo)

        result = await service.create_plan(
            _plan_payload(name="Free", slug="free", price_monthly=Decimal("0"))
        )

        assert result is created

    @pytest.mark.parametrize("price", ["1000", "50000000"])
    async def test_create_allows_exact_boundaries(self, price: str) -> None:
        created = PlanStub(id=uuid.uuid4())
        repo = _repo(get_plan_by_name=None, get_plan_by_slug=None, create_plan=created)
        service = AdminService(db=AsyncMock(), repo=repo)

        result = await service.create_plan(_plan_payload(price_monthly=Decimal(price)))

        assert result is created

    async def test_create_rejects_before_touching_the_repository(self) -> None:
        """Giá sai thì dừng ngay, đừng tốn hai lượt truy vấn trùng tên/mã."""
        repo = _repo(get_plan_by_name=None, get_plan_by_slug=None)
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(ValidationError):
            await service.create_plan(_plan_payload(price_monthly=Decimal("200")))

        repo.get_plan_by_name.assert_not_awaited()

    async def test_update_rejects_price_below_momo_minimum(self) -> None:
        plan = PlanStub(id=uuid.uuid4())
        repo = _repo(get_plan=plan)
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(ValidationError):
            await service.update_plan(
                plan.id, AdminUpdatePlanRequest(price_monthly=Decimal("200"))
            )

    async def test_update_without_price_field_is_unaffected(self) -> None:
        """Gói cũ đang để giá xấu vẫn phải đổi tên / tắt được.

        Chặn cả những lần sửa không đụng tới giá là khoá luôn con đường duy nhất để đi
        dọn đúng cái gói hỏng đó.
        """
        plan = PlanStub(id=uuid.uuid4(), name="abc", slug="abc", price_monthly=Decimal("200"))
        repo = _repo(get_plan=plan)
        service = AdminService(db=AsyncMock(), repo=repo)

        result = await service.update_plan(plan.id, AdminUpdatePlanRequest(is_active=False))

        assert result.is_active is False
        assert result.price_monthly == Decimal("200")


# ---------------------------------------------------------------------------
# Xoá gói
#
# Một gói là hai thứ cùng lúc: mặt hàng đang bày bán, và sự thật lịch sử gắn vào hoá đơn.
# Bỏ khỏi quầy thì lúc nào cũng được; xoá sự thật lịch sử thì không bao giờ.
# ---------------------------------------------------------------------------


class TestDeletePlan:
    async def test_deletes_a_plan_nobody_ever_used(self) -> None:
        """Ca "lỡ tay tạo nhầm" — không có lịch sử nào để phá."""
        plan = PlanStub(id=uuid.uuid4(), name="abc", slug="abc")
        repo = _repo(get_plan=plan, count_plan_usage=(0, 0))
        service = AdminService(db=AsyncMock(), repo=repo)

        await service.delete_plan(plan.id)

        repo.delete_plan.assert_awaited_once_with(plan)

    async def test_writes_audit_log_before_deleting(self) -> None:
        """Nhật ký phải sống sót sau khi gói biến mất — đó là toàn bộ điểm của nó."""
        plan = PlanStub(id=uuid.uuid4(), name="abc", slug="abc")
        repo = _repo(get_plan=plan, count_plan_usage=(0, 0))
        service = AdminService(db=AsyncMock(), repo=repo)

        await service.delete_plan(plan.id, admin_id=uuid.uuid4())

        repo.create_audit_log.assert_awaited_once()
        assert repo.create_audit_log.await_args.kwargs["event_type"] == "plan.deleted"

    async def test_refuses_when_someone_is_subscribed(self) -> None:
        plan = PlanStub(id=uuid.uuid4(), name="Pro", slug="pro")
        repo = _repo(get_plan=plan, count_plan_usage=(3, 0))
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(BusinessRuleError) as excinfo:
            await service.delete_plan(plan.id)

        assert "3" in excinfo.value.message
        repo.delete_plan.assert_not_awaited()

    async def test_refuses_when_plan_has_payment_history_even_with_no_subscribers(self) -> None:
        """Không còn ai dùng, nhưng từng có người trả tiền → hoá đơn cũ vẫn trỏ về đây."""
        plan = PlanStub(id=uuid.uuid4(), name="Pro cũ", slug="pro-cu")
        repo = _repo(get_plan=plan, count_plan_usage=(0, 5))
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(BusinessRuleError):
            await service.delete_plan(plan.id)

        repo.delete_plan.assert_not_awaited()

    async def test_refuses_to_delete_the_free_plan(self) -> None:
        """Free là gói hệ thống: đích đăng ký mới VÀ đích hạ gói khi hết hạn."""
        plan = PlanStub(id=uuid.uuid4(), name="Free", slug="free")
        repo = _repo(get_plan=plan, count_plan_usage=(0, 0))
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(BusinessRuleError) as excinfo:
            await service.delete_plan(plan.id)

        assert "Free" in excinfo.value.message
        repo.delete_plan.assert_not_awaited()

    async def test_checks_system_plan_before_counting_usage(self) -> None:
        """Gói Free bị chặn vì nó LÀ gói Free, không phải vì tình cờ có người dùng."""
        plan = PlanStub(id=uuid.uuid4(), name="Free", slug="free")
        repo = _repo(get_plan=plan, count_plan_usage=(0, 0))
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(BusinessRuleError):
            await service.delete_plan(plan.id)

        repo.count_plan_usage.assert_not_awaited()

    async def test_not_found_raises(self) -> None:
        repo = _repo(get_plan=None)
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(NotFoundError):
            await service.delete_plan(uuid.uuid4())


class TestSystemPlanGuards:
    """Gói Free vẫn đổi tên / đổi quyền lợi được — chỉ cấm hai thứ khiến code không
    tìm thấy nó nữa."""

    async def test_cannot_deactivate_the_free_plan(self) -> None:
        plan = PlanStub(id=uuid.uuid4(), name="Free", slug="free")
        repo = _repo(get_plan=plan)
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(BusinessRuleError):
            await service.update_plan(plan.id, AdminUpdatePlanRequest(is_active=False))

    async def test_cannot_change_the_free_plan_slug(self) -> None:
        plan = PlanStub(id=uuid.uuid4(), name="Free", slug="free")
        repo = _repo(get_plan=plan, get_plan_by_slug=None)
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(BusinessRuleError):
            await service.update_plan(plan.id, AdminUpdatePlanRequest(slug="mien-phi"))

    async def test_can_still_rename_the_free_plan(self) -> None:
        """Tên là để hiển thị — đổi thoải mái. Mã mới là khoá code."""
        plan = PlanStub(id=uuid.uuid4(), name="Free", slug="free")
        repo = _repo(get_plan=plan, get_plan_by_name=None)
        service = AdminService(db=AsyncMock(), repo=repo)

        result = await service.update_plan(plan.id, AdminUpdatePlanRequest(name="Miễn phí"))

        assert result.name == "Miễn phí"
        assert result.slug == "free"

    async def test_can_reactivate_the_free_plan(self) -> None:
        """Chỉ chặn TẮT, không chặn bật lại."""
        plan = PlanStub(id=uuid.uuid4(), name="Free", slug="free", is_active=False)
        repo = _repo(get_plan=plan)
        service = AdminService(db=AsyncMock(), repo=repo)

        result = await service.update_plan(plan.id, AdminUpdatePlanRequest(is_active=True))

        assert result.is_active is True

    async def test_other_plans_can_still_be_deactivated(self) -> None:
        plan = PlanStub(id=uuid.uuid4(), name="Pro", slug="pro")
        repo = _repo(get_plan=plan)
        service = AdminService(db=AsyncMock(), repo=repo)

        result = await service.update_plan(plan.id, AdminUpdatePlanRequest(is_active=False))

        assert result.is_active is False


# ---------------------------------------------------------------------------
# list_subscriptions_paginated
# ---------------------------------------------------------------------------


async def test_list_subscriptions_paginated_passes_filters_through() -> None:
    repo = _repo(list_subscriptions_paginated=([], 0))
    service = AdminService(db=AsyncMock(), repo=repo)

    await service.list_subscriptions_paginated(status="active", plan_slug="pro")

    repo.list_subscriptions_paginated.assert_awaited_once_with(
        status="active",
        plan_slug="pro",
        sort_by="created_at",
        sort_order="desc",
        page=1,
        page_size=20,
    )


# ---------------------------------------------------------------------------
# override_subscription
# ---------------------------------------------------------------------------


class TestOverrideSubscription:
    async def test_success_overrides_plan_and_expiry(self) -> None:
        new_plan_id = uuid.uuid4()
        sub = SubscriptionStub(id=uuid.uuid4(), plan_id=uuid.uuid4())
        plan = PlanStub(id=new_plan_id)
        repo = _repo(get_subscription=sub, get_plan=plan)
        service = AdminService(db=AsyncMock(), repo=repo)
        expires_at = datetime.now(UTC) + timedelta(days=30)

        result_sub, result_plan = await service.override_subscription(
            sub.id,
            AdminSubscriptionOverrideRequest(plan_id=new_plan_id, override_expires_at=expires_at),
            uuid.uuid4(),
        )

        assert result_sub.plan_id == new_plan_id
        assert result_sub.override_expires_at == expires_at
        assert result_plan is plan

    async def test_subscription_not_found_raises(self) -> None:
        repo = _repo(get_subscription=None)
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(NotFoundError):
            await service.override_subscription(
                uuid.uuid4(), AdminSubscriptionOverrideRequest(), uuid.uuid4()
            )

    async def test_resulting_plan_not_found_raises(self) -> None:
        sub = SubscriptionStub(id=uuid.uuid4(), plan_id=uuid.uuid4())
        repo = _repo(get_subscription=sub, get_plan=None)
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(NotFoundError):
            await service.override_subscription(
                sub.id, AdminSubscriptionOverrideRequest(), uuid.uuid4()
            )

    async def test_past_expiry_raises(self) -> None:
        sub = SubscriptionStub(id=uuid.uuid4(), plan_id=uuid.uuid4())
        repo = _repo(get_subscription=sub)
        service = AdminService(db=AsyncMock(), repo=repo)
        past = datetime.now(UTC) - timedelta(days=1)

        with pytest.raises(OverrideExpiryInPastError):
            await service.override_subscription(
                sub.id,
                AdminSubscriptionOverrideRequest(override_expires_at=past),
                uuid.uuid4(),
            )

        repo.save.assert_not_awaited()


# ---------------------------------------------------------------------------
# list_audit_logs_paginated
# ---------------------------------------------------------------------------


async def test_list_audit_logs_paginated_passes_filters_through() -> None:
    repo = _repo(list_audit_logs_paginated=([], 0))
    service = AdminService(db=AsyncMock(), repo=repo)

    await service.list_audit_logs_paginated(event_type="user.suspended")

    repo.list_audit_logs_paginated.assert_awaited_once_with(
        event_type="user.suspended",
        target_type=None,
        from_date=None,
        to_date=None,
        sort_by="occurred_at",
        sort_order="desc",
        page=1,
        page_size=20,
    )


# ---------------------------------------------------------------------------
# AI costs
# ---------------------------------------------------------------------------


async def test_list_ai_costs_paginated_passes_filters_through() -> None:
    repo = _repo(list_ai_costs_paginated=([], 0))
    service = AdminService(db=AsyncMock(), repo=repo)

    await service.list_ai_costs_paginated(ai_module="lead_qualifier")

    repo.list_ai_costs_paginated.assert_awaited_once_with(
        ai_module="lead_qualifier",
        from_date=None,
        to_date=None,
        sort_by="occurred_at",
        sort_order="desc",
        page=1,
        page_size=20,
    )


async def test_get_ai_cost_totals_returns_repo_result() -> None:
    totals = {"input_tokens": 10, "output_tokens": 20, "estimated_cost_usd": Decimal("0.01")}
    repo = _repo(get_ai_cost_totals=totals)
    service = AdminService(db=AsyncMock(), repo=repo)

    assert await service.get_ai_cost_totals() == totals


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


async def test_list_templates_returns_repo_result() -> None:
    templates = [TemplateStub(id=uuid.uuid4())]
    repo = _repo(list_templates=templates)
    service = AdminService(db=AsyncMock(), repo=repo)

    assert await service.list_templates() == templates


async def test_create_template_returns_created_row() -> None:
    created = TemplateStub(id=uuid.uuid4())
    repo = _repo(create_template=created)
    service = AdminService(db=AsyncMock(), repo=repo)

    payload = AdminCreateTemplateRequest(
        name="Default Proposal", template_type="proposal", content={"body": "..."}
    )
    result = await service.create_template(payload, admin_id=uuid.uuid4())

    assert result is created


class TestUpdateTemplate:
    async def test_success_bumps_version_on_content_change(self) -> None:
        template = TemplateStub(id=uuid.uuid4(), version_number=1)
        repo = _repo(get_template=template)
        service = AdminService(db=AsyncMock(), repo=repo)

        result = await service.update_template(
            template.id, AdminUpdateTemplateRequest(content={"body": "v2"})
        )

        assert result.content == {"body": "v2"}
        assert result.version_number == 2

    async def test_not_found_raises(self) -> None:
        repo = _repo(get_template=None)
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(NotFoundError):
            await service.update_template(uuid.uuid4(), AdminUpdateTemplateRequest(name="X"))


class TestDeleteTemplate:
    async def test_success_deletes_and_writes_audit_log(self) -> None:
        template = TemplateStub(id=uuid.uuid4(), name="Default Proposal")
        repo = _repo(get_template=template, count_child_templates=0)
        service = AdminService(db=AsyncMock(), repo=repo)
        admin_id = uuid.uuid4()

        await service.delete_template(template.id, admin_id=admin_id)

        repo.delete_template.assert_awaited_once_with(template)
        kwargs = repo.create_audit_log.await_args.kwargs
        assert kwargs["event_type"] == "template.deleted"
        assert kwargs["actor_user_id"] == admin_id
        assert kwargs["target_id"] == template.id
        assert "Default Proposal" in kwargs["description"]

    async def test_not_found_raises(self) -> None:
        repo = _repo(get_template=None)
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(NotFoundError):
            await service.delete_template(uuid.uuid4())

    async def test_template_with_children_raises_business_rule(self) -> None:
        template = TemplateStub(id=uuid.uuid4(), name="Base")
        repo = _repo(get_template=template, count_child_templates=2)
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(BusinessRuleError, match="2 mẫu phái sinh"):
            await service.delete_template(template.id)

        repo.delete_template.assert_not_awaited()

    async def test_blocked_delete_writes_no_audit_log(self) -> None:
        template = TemplateStub(id=uuid.uuid4(), name="Base")
        repo = _repo(get_template=template, count_child_templates=1)
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(BusinessRuleError):
            await service.delete_template(template.id)

        repo.create_audit_log.assert_not_awaited()


# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------


async def test_list_feature_flags_returns_repo_result() -> None:
    flags = [FeatureFlagStub(id=uuid.uuid4())]
    repo = _repo(list_feature_flags=flags)
    service = AdminService(db=AsyncMock(), repo=repo)

    assert await service.list_feature_flags() == flags


class TestUpdateFeatureFlag:
    async def test_success(self) -> None:
        flag = FeatureFlagStub(id=uuid.uuid4(), is_enabled=False, rollout_percentage=0)
        repo = _repo(get_feature_flag_by_name=flag)
        service = AdminService(db=AsyncMock(), repo=repo)

        result = await service.update_feature_flag(
            flag.flag_name,
            AdminUpdateFeatureFlagRequest(is_enabled=True, rollout_percentage=50),
        )

        assert result.is_enabled is True
        assert result.rollout_percentage == 50

    async def test_not_found_raises(self) -> None:
        repo = _repo(get_feature_flag_by_name=None)
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(NotFoundError):
            await service.update_feature_flag(
                "missing_flag", AdminUpdateFeatureFlagRequest(is_enabled=True)
            )

    async def test_invalid_rollout_percentage_raises(self) -> None:
        """Belt-and-suspenders: the request schema already bounds this to
        [0, 100], but the domain entity enforces it independently too."""
        flag = FeatureFlagStub(id=uuid.uuid4())
        repo = _repo(get_feature_flag_by_name=flag)
        service = AdminService(db=AsyncMock(), repo=repo)
        payload = AdminUpdateFeatureFlagRequest.model_construct(
            is_enabled=None, rollout_percentage=150, target_user_ids=None, description=None
        )

        with pytest.raises(InvalidRolloutPercentageError):
            await service.update_feature_flag(flag.flag_name, payload)

        repo.save.assert_not_awaited()


# ---------------------------------------------------------------------------
# Platform metrics
# ---------------------------------------------------------------------------


async def test_get_platform_metrics_returns_repo_result() -> None:
    metrics = {"total_users": 5}
    repo = _repo(get_platform_metrics=metrics)
    service = AdminService(db=AsyncMock(), repo=repo)

    assert await service.get_platform_metrics() == metrics


# ---------------------------------------------------------------------------
# AI provider configuration
# ---------------------------------------------------------------------------


@dataclass
class AIProviderConfigStub:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    llm_provider: str = "groq"
    llm_model: str = "openai/gpt-oss-120b"
    updated_by: uuid.UUID | None = None


def _ai_repo(configuration: AIProviderConfigStub | None) -> AsyncMock:
    repo = _repo(get_ai_provider_configuration=configuration)
    repo.update_ai_provider_configuration.side_effect = lambda obj: obj
    return repo


class TestGetAiProviderConfiguration:
    async def test_returns_configuration(self) -> None:
        configuration = AIProviderConfigStub()
        service = AdminService(db=AsyncMock(), repo=_ai_repo(configuration))

        assert await service.get_ai_provider_configuration() is configuration

    async def test_missing_configuration_raises(self) -> None:
        service = AdminService(db=AsyncMock(), repo=_ai_repo(None))

        with pytest.raises(NotFoundError):
            await service.get_ai_provider_configuration()


class TestUpdateAiProviderConfiguration:
    @pytest.fixture(autouse=True)
    def _provider_api_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Ghim khoá API giả cho mọi nhà cung cấp có dùng khoá.

        `update_ai_provider_configuration` giờ DỰNG THỬ provider trước khi ghi, mà
        GroqProvider/GeminiProvider ném RuntimeError khi khoá trống. Không ghim thì
        các test này xanh ở máy dev (có `.env`) và đỏ trên CI — job test không đặt
        GROQ_API_KEY/GEMINI_API_KEY. Ollama xác thực bằng `ollama_base_url`, không
        có trường khoá, nên phải kiểm tra trước khi gán: Settings là pydantic model
        và gán tên lạ sẽ lỗi.
        """
        from src.ai.shared.constants import SUPPORTED_LLM_PROVIDERS
        from src.config.settings import settings

        for name in SUPPORTED_LLM_PROVIDERS:
            field = f"{name}_api_key"
            if field in type(settings).model_fields:
                monkeypatch.setattr(settings, field, f"test-{name}-key")

    @pytest.mark.parametrize(
        ("provider", "model"),
        [
            ("groq", "openai/gpt-oss-120b"),
            ("gemini", "gemini-2.5-flash"),
            ("gemini", "gemini-3.5-flash-lite"),
            ("ollama", "qwen3:4b"),
        ],
    )
    async def test_every_supported_pair_is_accepted(self, provider: str, model: str) -> None:
        """Every pair in SUPPORTED_LLM_MODELS must be accepted — ollama included."""
        configuration = AIProviderConfigStub()
        repo = _ai_repo(configuration)
        admin_id = uuid.uuid4()
        service = AdminService(db=AsyncMock(), repo=repo)

        result = await service.update_ai_provider_configuration(
            llm_provider=provider, llm_model=model, admin_id=admin_id
        )

        assert result.llm_provider == provider
        assert result.llm_model == model
        assert result.updated_by == admin_id
        repo.create_audit_log.assert_awaited_once()

    async def test_audit_log_records_provider_and_model(self) -> None:
        repo = _ai_repo(AIProviderConfigStub())
        service = AdminService(db=AsyncMock(), repo=repo)

        await service.update_ai_provider_configuration(
            llm_provider="gemini", llm_model="gemini-2.5-flash", admin_id=uuid.uuid4()
        )

        kwargs = repo.create_audit_log.await_args.kwargs
        assert kwargs["event_type"] == "ai_provider.updated"
        assert "gemini/gemini-2.5-flash" in kwargs["description"]

    async def test_unsupported_provider_raises(self) -> None:
        repo = _ai_repo(AIProviderConfigStub())
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(ValidationError):
            await service.update_ai_provider_configuration(
                llm_provider="openai", llm_model="gpt-4o", admin_id=uuid.uuid4()
            )

        repo.update_ai_provider_configuration.assert_not_awaited()
        repo.create_audit_log.assert_not_awaited()

    @pytest.mark.parametrize(
        ("provider", "model"),
        [
            ("groq", "gemini-2.5-flash"),
            ("gemini", "openai/gpt-oss-120b"),
            ("ollama", "gemini-2.5-flash"),
        ],
    )
    async def test_model_belonging_to_another_provider_raises(
        self, provider: str, model: str
    ) -> None:
        repo = _ai_repo(AIProviderConfigStub())
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(ValidationError):
            await service.update_ai_provider_configuration(
                llm_provider=provider, llm_model=model, admin_id=uuid.uuid4()
            )

        repo.update_ai_provider_configuration.assert_not_awaited()

    async def test_unknown_model_raises(self) -> None:
        repo = _ai_repo(AIProviderConfigStub())
        service = AdminService(db=AsyncMock(), repo=repo)

        with pytest.raises(ValidationError):
            await service.update_ai_provider_configuration(
                llm_provider="groq", llm_model="not-a-real-model", admin_id=uuid.uuid4()
            )

    async def test_provider_and_model_are_normalised(self) -> None:
        """The service lowercases the provider and strips padding off the model."""
        configuration = AIProviderConfigStub()
        service = AdminService(db=AsyncMock(), repo=_ai_repo(configuration))

        result = await service.update_ai_provider_configuration(
            llm_provider="  GROQ  ".strip(),
            llm_model="  openai/gpt-oss-120b  ",
            admin_id=uuid.uuid4(),
        )

        assert result.llm_provider == "groq"
        assert result.llm_model == "openai/gpt-oss-120b"

    async def test_missing_configuration_raises(self) -> None:
        service = AdminService(db=AsyncMock(), repo=_ai_repo(None))

        with pytest.raises(NotFoundError):
            await service.update_ai_provider_configuration(
                llm_provider="groq",
                llm_model="openai/gpt-oss-120b",
                admin_id=uuid.uuid4(),
            )
