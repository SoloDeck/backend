"""Seed development admin account.

Only executes when APP_ENV=development.
Creates admin@solodesk.dev if the account does not already exist.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from src.infrastructure.database.models import PlanModel, SubscriptionModel, UserModel
from src.shared.security.passwords import hash_password

from .base import BaseSeeder

ADMIN_EMAIL = "admin@solodesk.dev"
ADMIN_PASSWORD = "Admin@SoloDesk2025!"
ADMIN_FULL_NAME = "SoloDesk Admin"


class AdminSeeder(BaseSeeder):
    name = "admin"

    async def run(self) -> None:
        self._log.info("seeder.start", email=ADMIN_EMAIL)

        existing = await self.db.scalar(select(UserModel).where(UserModel.email == ADMIN_EMAIL))
        if existing is not None:
            self._log.info("seeder.skip", reason="admin already exists")
            return

        now = datetime.now(UTC)
        admin_id = uuid.uuid4()

        admin = UserModel(
            id=admin_id,
            email=ADMIN_EMAIL,
            full_name=ADMIN_FULL_NAME,
            role="admin",
            status="active",
            hashed_password=hash_password(ADMIN_PASSWORD),
            locale="vi",
            timezone="Asia/Ho_Chi_Minh",
            notification_channel="email",
            theme="light",
        )
        self.db.add(admin)
        await self.db.flush()

        free_plan = await self.db.scalar(select(PlanModel).where(PlanModel.slug == "free"))
        if free_plan is not None:
            subscription = SubscriptionModel(
                user_id=admin_id,
                plan_id=free_plan.id,
                status="active",
                current_period_start=now,
                current_period_end=now + timedelta(days=36500),
            )
            self.db.add(subscription)

        await self._commit()
        self._log.info("seeder.done", admin_id=str(admin_id))
