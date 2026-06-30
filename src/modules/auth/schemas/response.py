from pydantic import BaseModel


class AuthTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int  # seconds


class MessageResponse(BaseModel):
    detail: str


class ClientConfigResponse(BaseModel):
    app_env: str
    google_web_client_id: str
