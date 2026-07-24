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
from src.shared.exceptions.domain import AlreadyExistsError, NotFoundError


@dataclass
class UserStub:
    id: uuid.UUID
    email: str = "user@example.com"
    role: str = "freelancer"
    status: str = "active"
    full_name: str = "Test User"
    phone: str | None = None
    deleted_at: datetime | None = None


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


@dataclass
class RefreshTokenStub:
    token_hash: str
    expires_at: datetime


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
    async def test_blacklists_every_active_token(self) -> None:
        user_id = uuid.uuid4()
        tokens = [
            RefreshTokenStub(token_hash="jti-1", expires_at=datetime.now(UTC) + timedelta(days=1)),
            RefreshTokenStub(token_hash="jti-2", expires_at=datetime.now(UTC) + timedelta(days=2)),
        ]
        repo = _repo(get_user_refresh_tokens=tokens)
        service = AdminService(db=AsyncMock(), repo=repo)

        await service.revoke_user_sessions(user_id)

        assert repo.blacklist_refresh_token.await_count == 2

    async def test_no_tokens_is_a_noop(self) -> None:
        repo = _repo(get_user_refresh_tokens=[])
        service = AdminService(db=AsyncMock(), repo=repo)

        await service.revoke_user_sessions(uuid.uuid4())

        repo.blacklist_refresh_token.assert_not_awaited()


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
