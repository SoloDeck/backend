"""Auth infrastructure — database access for tokens and OAuth identities."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import (
    OAuthIdentityModel,
    PasswordResetTokenModel,
    PlanModel,
    SubscriptionModel,
    TokenBlacklistModel,
    UserModel,
)


@dataclass
class AuthRepository:
    db: AsyncSession

    async def get_user_by_email(self, email: str):
        return await self.db.scalar(
            select(UserModel).where(
                UserModel.email == email,
                UserModel.deleted_at.is_(None),
            )
        )

    async def get_user_by_id(self, user_id: uuid.UUID):
        return await self.db.scalar(
            select(UserModel).where(
                UserModel.id == user_id,
                UserModel.deleted_at.is_(None),
            )
        )

    async def add_user(self, user: UserModel) -> None:
        self.db.add(user)

    async def get_free_plan(self):
        return await self.db.scalar(select(PlanModel).where(PlanModel.name == "Free"))

    async def get_plan(self, plan_id: uuid.UUID):
        return await self.db.scalar(select(PlanModel).where(PlanModel.id == plan_id))

    async def add_subscription(self, sub: SubscriptionModel) -> None:
        self.db.add(sub)

    async def get_subscription(self, user_id: uuid.UUID):
        return await self.db.scalar(
            select(SubscriptionModel).where(SubscriptionModel.user_id == user_id)
        )

    async def add_token_blacklist(self, entry: TokenBlacklistModel) -> None:
        self.db.add(entry)

    async def get_oauth_identity(self, provider: str, provider_sub: str):
        return await self.db.scalar(
            select(OAuthIdentityModel).where(
                OAuthIdentityModel.provider == provider,
                OAuthIdentityModel.provider_sub == provider_sub,
            )
        )

    async def add_oauth_identity(self, identity: OAuthIdentityModel) -> None:
        self.db.add(identity)

    async def get_reset_token(self, token_hash: str, now):
        return await self.db.scalar(
            select(PasswordResetTokenModel).where(
                PasswordResetTokenModel.token_hash == token_hash,
                PasswordResetTokenModel.used_at.is_(None),
                PasswordResetTokenModel.expires_at > now,
            )
        )

    async def add_reset_token(self, token: PasswordResetTokenModel) -> None:
        self.db.add(token)

    async def flush(self) -> None:
        await self.db.flush()

    async def refresh(self, obj) -> None:
        await self.db.refresh(obj)
