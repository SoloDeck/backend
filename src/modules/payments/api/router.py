"""Payments API — generic payment-intent endpoints.

Currently only resolves subscription-targeted intents (invoice payment-links
are contracted but not implemented yet).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.subscriptions.application.service import SubscriptionsService
from src.modules.subscriptions.schemas.response import PaymentIntentResponse
from src.shared.dependencies.auth import CurrentUserId
from src.shared.dependencies.payments import MomoClientDep
from src.shared.responses.response import ApiResponse

router = APIRouter()
DBSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/intents/{payment_intent_id}", response_model=ApiResponse[PaymentIntentResponse])
async def get_payment_intent(
    payment_intent_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
    momo_client: MomoClientDep,
) -> ApiResponse[PaymentIntentResponse]:
    """Tiêm cổng MoMo vào vì `get_checkout_status` giờ TỰ HỎI nhà cung cấp khi đơn còn
    `pending`, thay vì chỉ đọc DB rồi báo "đang chờ" mãi mãi.

    Chỉ tiêm MoMo: đó là cổng duy nhất hiện có hàm hỏi trạng thái. Cổng khác thiếu thì
    `_reconcile_pending_payment` lặng lẽ bỏ qua, hành vi y như trước.
    """
    payment = await SubscriptionsService(db=db, momo_client=momo_client).get_checkout_status(
        user_id, payment_intent_id
    )
    return ApiResponse.ok(PaymentIntentResponse.from_model(payment))


@router.post(
    "/intents/{payment_intent_id}/cancel", response_model=ApiResponse[PaymentIntentResponse]
)
async def cancel_payment_intent(
    payment_intent_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[PaymentIntentResponse]:
    payment = await SubscriptionsService(db=db).cancel_checkout(user_id, payment_intent_id)
    return ApiResponse.ok(PaymentIntentResponse.from_model(payment))
