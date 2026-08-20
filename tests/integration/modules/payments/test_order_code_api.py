"""`order_code` đi qua được DB thật — cột, unique index, và luồng checkout.

Migration b2c3d4e5f6a7 là thứ duy nhất tạo ra unique index. Không có test chạm DB thật
thì không có gì chứng minh nó đã chạy: `generate_order_code` cố tình KHÔNG có vòng thử
lại, nên unique index CHÍNH LÀ cơ chế chặn hai đơn mang cùng một mã.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import SubscriptionPaymentModel
from src.infrastructure.database.seeders.plans import PlansSeeder
from src.modules.subscriptions.domain.entities.subscription_payment import (
    ORDER_CODE_BODY_LENGTH,
    ORDER_CODE_PREFIX,
)
from tests.integration.modules.clients.test_clients_api import _auth_headers


async def _checkout(client: AsyncClient, headers: dict, plan_id: str) -> dict:
    resp = await client.post(
        "/api/v1/subscriptions/checkout",
        json={"plan_id": plan_id, "provider": "momo"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def test_checkout_persists_a_well_formed_order_code(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plans = await client.get("/api/v1/subscriptions/plans", headers=headers)
    plan = next(p for p in plans.json()["data"] if p["slug"] == "pro")

    payment = await _checkout(client, headers, plan["id"])

    row = await db_session.get(SubscriptionPaymentModel, payment["id"])
    assert row.order_code.startswith(ORDER_CODE_PREFIX)
    assert len(row.order_code) == len(ORDER_CODE_PREFIX) + ORDER_CODE_BODY_LENGTH


async def test_two_checkouts_get_different_order_codes(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plans = await client.get("/api/v1/subscriptions/plans", headers=headers)
    plan = next(p for p in plans.json()["data"] if p["slug"] == "pro")

    first = await _checkout(client, headers, plan["id"])
    second = await _checkout(client, headers, plan["id"])

    row_a = await db_session.get(SubscriptionPaymentModel, first["id"])
    row_b = await db_session.get(SubscriptionPaymentModel, second["id"])
    assert row_a.order_code != row_b.order_code


async def test_duplicate_order_code_is_rejected_by_the_database(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Chốt chặn thật nằm ở DB, không ở tầng ứng dụng.

    Hai đơn cùng mã nghĩa là một khoản tiền vào khớp nhầm đơn — hỏng nặng hơn nhiều so
    với một lần checkout thất bại. Test này chứng minh migration đã dựng đúng index.
    """
    await PlansSeeder(db_session).run()
    headers = await _auth_headers(client)
    plans = await client.get("/api/v1/subscriptions/plans", headers=headers)
    plan = next(p for p in plans.json()["data"] if p["slug"] == "pro")
    payment = await _checkout(client, headers, plan["id"])
    row = await db_session.get(SubscriptionPaymentModel, payment["id"])

    clone = SubscriptionPaymentModel(
        id=uuid.uuid4(),
        user_id=row.user_id,
        subscription_id=row.subscription_id,
        plan_id=row.plan_id,
        provider=row.provider,
        status=row.status,
        amount=row.amount,
        currency=row.currency,
        order_code=row.order_code,  # <-- trùng mã
        expires_at=row.expires_at,
    )
    db_session.add(clone)

    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()
