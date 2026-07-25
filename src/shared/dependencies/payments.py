from typing import Annotated

from fastapi import Depends

from src.config.settings import settings
from src.integrations.momo.client import MomoClient
from src.modules.subscriptions.application.payment_gateway import PaymentGateway


def get_momo_client() -> PaymentGateway:
    return MomoClient(
        partner_code=settings.momo_partner_code,
        access_key=settings.momo_access_key,
        secret_key=settings.momo_secret_key,
        partner_name=settings.momo_partner_name,
        store_id=settings.momo_store_id,
        endpoint=settings.momo_endpoint,
        request_type=settings.momo_request_type,
        lang=settings.momo_lang,
        redirect_url=settings.momo_redirect_url,
        timeout_seconds=settings.momo_timeout_seconds,
    )


MomoClientDep = Annotated[PaymentGateway, Depends(get_momo_client)]
