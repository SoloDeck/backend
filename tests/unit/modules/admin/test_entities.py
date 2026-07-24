import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.modules.admin.domain.entities import AdminUser, FeatureFlagRollout, SubscriptionOverride
from src.modules.admin.domain.exceptions import (
    InvalidRolloutPercentageError,
    LastAdminSuspensionError,
    OverrideExpiryInPastError,
)


class TestAdminUserSuspend:
    def test_suspends_freelancer(self) -> None:
        user = AdminUser(id=uuid.uuid4(), email="a@b.com", role="freelancer", status="active")

        user.suspend(is_last_active_admin=False)

        assert user.status == "suspended"

    def test_suspends_admin_when_not_last(self) -> None:
        user = AdminUser(id=uuid.uuid4(), email="a@b.com", role="admin", status="active")

        user.suspend(is_last_active_admin=False)

        assert user.status == "suspended"

    def test_blocks_last_admin(self) -> None:
        user = AdminUser(id=uuid.uuid4(), email="a@b.com", role="admin", status="active")

        with pytest.raises(LastAdminSuspensionError):
            user.suspend(is_last_active_admin=True)

        assert user.status == "active"


def test_admin_user_reinstate() -> None:
    user = AdminUser(id=uuid.uuid4(), email="a@b.com", role="freelancer", status="suspended")

    user.reinstate()

    assert user.status == "active"


class TestSubscriptionOverride:
    def test_accepts_future_expiry(self) -> None:
        expires_at = datetime.now(UTC) + timedelta(days=30)

        override = SubscriptionOverride(
            subscription_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            override_by_admin_id=uuid.uuid4(),
            override_expires_at=expires_at,
        )

        assert override.override_expires_at == expires_at

    def test_accepts_no_expiry(self) -> None:
        override = SubscriptionOverride(
            subscription_id=uuid.uuid4(),
            plan_id=uuid.uuid4(),
            override_by_admin_id=uuid.uuid4(),
            override_expires_at=None,
        )

        assert override.override_expires_at is None

    def test_rejects_past_expiry(self) -> None:
        past = datetime.now(UTC) - timedelta(days=1)

        with pytest.raises(OverrideExpiryInPastError):
            SubscriptionOverride(
                subscription_id=uuid.uuid4(),
                plan_id=uuid.uuid4(),
                override_by_admin_id=uuid.uuid4(),
                override_expires_at=past,
            )


class TestFeatureFlagRollout:
    def test_rejects_out_of_range_percentage(self) -> None:
        with pytest.raises(InvalidRolloutPercentageError):
            FeatureFlagRollout(
                flag_name="f", is_enabled=True, rollout_percentage=101, target_user_ids=None
            )

    def test_rejects_negative_percentage(self) -> None:
        with pytest.raises(InvalidRolloutPercentageError):
            FeatureFlagRollout(
                flag_name="f", is_enabled=True, rollout_percentage=-1, target_user_ids=None
            )

    def test_disabled_flag_is_never_enabled_for_anyone(self) -> None:
        flag = FeatureFlagRollout(
            flag_name="f", is_enabled=False, rollout_percentage=100, target_user_ids=None
        )

        assert flag.is_enabled_for_user(uuid.uuid4()) is False

    def test_hundred_percent_rollout_enables_everyone(self) -> None:
        flag = FeatureFlagRollout(
            flag_name="f", is_enabled=True, rollout_percentage=100, target_user_ids=None
        )

        assert flag.is_enabled_for_user(uuid.uuid4()) is True

    def test_zero_percent_rollout_disables_everyone_not_targeted(self) -> None:
        flag = FeatureFlagRollout(
            flag_name="f", is_enabled=True, rollout_percentage=0, target_user_ids=None
        )

        assert flag.is_enabled_for_user(uuid.uuid4()) is False

    def test_target_user_ids_override_zero_rollout(self) -> None:
        target = uuid.uuid4()
        flag = FeatureFlagRollout(
            flag_name="f", is_enabled=True, rollout_percentage=0, target_user_ids=[target]
        )

        assert flag.is_enabled_for_user(target) is True
        assert flag.is_enabled_for_user(uuid.uuid4()) is False

    def test_resolution_is_deterministic_for_same_user(self) -> None:
        flag = FeatureFlagRollout(
            flag_name="f", is_enabled=True, rollout_percentage=50, target_user_ids=None
        )
        user_id = uuid.uuid4()

        first = flag.is_enabled_for_user(user_id)
        second = flag.is_enabled_for_user(user_id)

        assert first == second
