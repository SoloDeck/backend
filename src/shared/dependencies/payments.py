from typing import Annotated

from fastapi import Depends

from src.integrations.momo.client import MockMomoClient
from src.modules.subscriptions.application.payment_gateway import PaymentGateway


def get_momo_client() -> PaymentGateway:
    return MockMomoClient()


MomoClientDep = Annotated[PaymentGateway, Depends(get_momo_client)]
