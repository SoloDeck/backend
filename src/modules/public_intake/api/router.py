"""Public intake placeholder router for Phase 6.1 contract alignment.

Full public lead capture is owned by Phase 6.6. This endpoint is intentionally
registered now so the OpenAPI public path is not contract-only drift.
"""

from fastapi import APIRouter, status
from pydantic import BaseModel
from starlette.responses import JSONResponse


router = APIRouter()


class PublicIntakePayload(BaseModel):
    inquiry_text: str | None = None


@router.post("/intake/{share_token}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def submit_public_intake(share_token: str, payload: PublicIntakePayload) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={
            "success": False,
            "code": status.HTTP_501_NOT_IMPLEMENTED,
            "error": {
                "message": "Public intake capture is scheduled for Phase 6.6",
            },
        },
    )
