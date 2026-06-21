"""Clients API api."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.clients.application.service import ClientsService
from src.modules.clients.schemas.request import ClientRequest, CommLogRequest
from src.modules.clients.schemas.response import (
    ClientResponse,
    CommLogResponse,
    MessageResponse,
)
from src.shared.dependencies.auth import CurrentUserId
from src.shared.responses.response import ApiResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.post("", response_model=ApiResponse[ClientResponse], status_code=201)
async def create_client(
    payload: ClientRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ClientResponse]:
    client = await ClientsService(db=db).create(user_id, payload)
    return ApiResponse.created(ClientResponse.model_validate(client))


@router.get("", response_model=ApiResponse[list[ClientResponse]])
async def list_clients(
    user_id: CurrentUserId,
    db: DBSession,
    status: str | None = Query(default=None, description="Filter by status: prospect, active, inactive, archived"),
    name: str | None = Query(default=None, description="Search by name (case-insensitive, partial match)"),
    email: str | None = Query(default=None, description="Search by email (case-insensitive, partial match)"),
) -> ApiResponse[list[ClientResponse]]:
    clients = await ClientsService(db=db).list_all(user_id, status=status, name=name, email=email)
    return ApiResponse.ok([ClientResponse.model_validate(c) for c in clients])


@router.get("/{client_id}", response_model=ApiResponse[ClientResponse])
async def get_client(
    client_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ClientResponse]:
    client = await ClientsService(db=db).get_one(user_id, client_id)
    return ApiResponse.ok(ClientResponse.model_validate(client))


@router.patch("/{client_id}", response_model=ApiResponse[ClientResponse])
async def update_client(
    client_id: uuid.UUID,
    payload: ClientRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ClientResponse]:
    client = await ClientsService(db=db).update(user_id, client_id, payload)
    return ApiResponse.ok(ClientResponse.model_validate(client))


@router.delete("/{client_id}", response_model=ApiResponse[MessageResponse])
async def delete_client(
    client_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[MessageResponse]:
    await ClientsService(db=db).delete(user_id, client_id)
    return ApiResponse.ok(MessageResponse(detail="Client deleted"))


@router.post("/{client_id}/comm-logs", response_model=ApiResponse[CommLogResponse], status_code=201)
async def add_comm_log(
    client_id: uuid.UUID,
    payload: CommLogRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[CommLogResponse]:
    log = await ClientsService(db=db).add_comm_log(user_id, client_id, payload)
    return ApiResponse.created(CommLogResponse.model_validate(log))


@router.get("/{client_id}/comm-logs", response_model=ApiResponse[list[CommLogResponse]])
async def list_comm_logs(
    client_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[list[CommLogResponse]]:
    logs = await ClientsService(db=db).list_comm_logs(user_id, client_id)
    return ApiResponse.ok([CommLogResponse.model_validate(log) for log in logs])


