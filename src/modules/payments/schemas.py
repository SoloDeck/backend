from pydantic import BaseModel


class PaymentWebhookAcceptedResponse(BaseModel):
    accepted: bool
    event_id: str
