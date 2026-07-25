"""Payment provider webhook callbacks — no authentication.

A provider's server (real or, here, our mock simulate script) can't present a
SoloDesk JWT. The request body is the provider's raw native payload, not the
contract's generic PaymentWebhookRequest envelope — a real provider's server
sends its own documented fields and can't be made to wrap them for us.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.payments.schemas import PaymentWebhookAcceptedResponse
from src.modules.subscriptions.application.service import SubscriptionsService
from src.modules.subscriptions.domain.entities.subscription_payment import PaymentProvider
from src.shared.dependencies.payments import MomoClientDep
from src.shared.exceptions.domain import DomainError
from src.shared.responses.response import ApiResponse

router = APIRouter()
DBSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.post(
    "/{provider}", response_model=ApiResponse[PaymentWebhookAcceptedResponse], status_code=202
)
async def receive_payment_webhook(
    provider: str,
    payload: dict[str, Any],
    db: DBSession,
    momo_client: MomoClientDep,
) -> ApiResponse[PaymentWebhookAcceptedResponse]:
    try:
        provider_enum = PaymentProvider(provider)
    except ValueError as exc:
        raise DomainError(f"Unsupported payment provider '{provider}'") from exc

    await SubscriptionsService(db=db, momo_client=momo_client).handle_payment_callback(
        provider_enum, payload
    )
    event_id = str(payload.get("orderId", ""))
    return ApiResponse.ok(PaymentWebhookAcceptedResponse(accepted=True, event_id=event_id), code=202)
