"""Clients API router."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.clients.application.service import ClientsService
from src.modules.clients.schemas.request import ClientRequest, CommLogRequest, TagRequest
from src.modules.clients.schemas.response import (
    ClientResponse,
    CommLogResponse,
    MessageResponse,
    TagResponse,
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
) -> ApiResponse[list[ClientResponse]]:
    clients = await ClientsService(db=db).list_all(user_id)
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
    return ApiResponse.ok([CommLogResponse.model_validate(l) for l in logs])


@router.post("/{client_id}/tags", response_model=ApiResponse[TagResponse], status_code=201)
async def add_tag(
    client_id: uuid.UUID,
    payload: TagRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[TagResponse]:
    tag = await ClientsService(db=db).add_tag(user_id, client_id, payload)
    return ApiResponse.created(TagResponse.model_validate(tag))


@router.get("/{client_id}/tags", response_model=ApiResponse[list[TagResponse]])
async def list_tags(
    client_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[list[TagResponse]]:
    tags = await ClientsService(db=db).list_tags(user_id, client_id)
    return ApiResponse.ok([TagResponse.model_validate(t) for t in tags])


@router.delete("/{client_id}/tags/{tag}", response_model=ApiResponse[MessageResponse])
async def remove_tag(
    client_id: uuid.UUID,
    tag: str,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[MessageResponse]:
    await ClientsService(db=db).remove_tag(user_id, client_id, tag)
    return ApiResponse.ok(MessageResponse(detail="Tag removed"))
