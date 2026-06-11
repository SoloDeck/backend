"""Seed sample clients for the development admin account.

Creates one client per status (prospect, active, inactive, archived) so that
status-filtering can be manually tested end-to-end.
Only executes when APP_ENV=development.
"""

from sqlalchemy import select

from src.infrastructure.database.models import ClientModel, UserModel

from .base import BaseSeeder

ADMIN_EMAIL = "admin@solodesk.dev"

SAMPLE_CLIENTS = [
    {
        "name": "Nguyen Van An",
        "email": "an.nguyen@example.com",
        "phone": "+84901000001",
        "type": "individual",
        "status": "prospect",
        "address_city": "Hanoi",
        "address_country": "VN",
        "description": "Freelance graphic designer looking for branding services.",
    },
    {
        "name": "Tech Solutions JSC",
        "email": "contact@techsolutions.vn",
        "phone": "+84901000002",
        "type": "company",
        "status": "active",
        "address_city": "Ho Chi Minh City",
        "address_country": "VN",
        "description": "Software outsourcing company, 50+ employees.",
    },
    {
        "name": "Le Thi Bich",
        "email": "bich.le@example.com",
        "phone": "+84901000003",
        "type": "individual",
        "status": "inactive",
        "address_city": "Da Nang",
        "address_country": "VN",
        "description": "Previous client, project completed in 2024.",
    },
    {
        "name": "Old Corp Ltd",
        "email": "hello@oldcorp.vn",
        "phone": "+84901000004",
        "type": "company",
        "status": "archived",
        "address_city": "Can Tho",
        "address_country": "VN",
        "description": "No longer operating. Archived for record-keeping.",
    },
]


class ClientsSeeder(BaseSeeder):
    name = "clients"

    async def run(self) -> None:
        self._log.info("seeder.start", admin_email=ADMIN_EMAIL)

        admin = await self.db.scalar(
            select(UserModel).where(UserModel.email == ADMIN_EMAIL)
        )
        if admin is None:
            self._log.info("seeder.skip", reason="admin user not found — run AdminSeeder first")
            return

        existing_count = await self.db.scalar(
            select(ClientModel)
            .where(ClientModel.owner_user_id == admin.id)
            .where(ClientModel.deleted_at.is_(None))
        )
        if existing_count is not None:
            self._log.info("seeder.skip", reason="clients already seeded for admin")
            return

        for data in SAMPLE_CLIENTS:
            self.db.add(ClientModel(owner_user_id=admin.id, **data))

        await self._commit()
        self._log.info("seeder.done", count=len(SAMPLE_CLIENTS))
