"""Users API api."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.users.application.service import UsersService
from src.modules.users.schemas.request import (
    ChangePasswordRequest,
    FreelancerProfileUpdateRequest,
    UpdatePreferencesRequest,
    UpdateProfessionalProfileRequest,
    UpdateUserRequest,
)
from src.modules.users.schemas.response import MessageResponse, UserResponse
from src.shared.dependencies.auth import CurrentUserId
from src.shared.responses.response import ApiResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/me", response_model=ApiResponse[UserResponse], summary="Get current user profile")
async def get_me(
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[UserResponse]:
    user = await UsersService(db=db).get_me(user_id)
    return ApiResponse.ok(UserResponse.model_validate(user))


@router.patch(
    "/me",
    response_model=ApiResponse[UserResponse],
    summary="Update current user profile",
)
async def update_me(
    payload: UpdateUserRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[UserResponse]:
    user = await UsersService(db=db).update_me(user_id, payload)
    return ApiResponse.ok(UserResponse.model_validate(user))


@router.delete(
    "/me",
    response_model=ApiResponse[MessageResponse],
    summary="Delete current user account",
)
async def delete_me(
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[MessageResponse]:
    await UsersService(db=db).delete_me(user_id)
    return ApiResponse.ok(MessageResponse(detail="Account deleted"))


@router.patch(
    "/me/freelancer-profile",
    response_model=ApiResponse[UserResponse],
    summary="Update public freelancer directory profile",
)
async def update_freelancer_profile(
    payload: FreelancerProfileUpdateRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[UserResponse]:
    user = await UsersService(db=db).update_freelancer_profile(user_id, payload)
    return ApiResponse.ok(UserResponse.model_validate(user))


@router.patch(
    "/me/professional-profile",
    response_model=ApiResponse[UserResponse],
    summary="Update professional profile (skills, rate, portfolio…)",
)
async def update_professional_profile(
    payload: UpdateProfessionalProfileRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[UserResponse]:
    user = await UsersService(db=db).update_professional_profile(user_id, payload)
    return ApiResponse.ok(UserResponse.model_validate(user))


@router.patch(
    "/me/preferences",
    response_model=ApiResponse[UserResponse],
    summary="Update notification, locale, and theme preferences",
)
async def update_preferences(
    payload: UpdatePreferencesRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[UserResponse]:
    user = await UsersService(db=db).update_preferences(user_id, payload)
    return ApiResponse.ok(UserResponse.model_validate(user))


@router.post(
    "/me/change-password",
    response_model=ApiResponse[MessageResponse],
    summary="Change current user password",
)
async def change_password(
    payload: ChangePasswordRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[MessageResponse]:
    await UsersService(db=db).change_password(user_id, payload)
    return ApiResponse.ok(MessageResponse(detail="Password changed successfully"))
