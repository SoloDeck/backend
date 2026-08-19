"""Reminders API api."""

import uuid
from types import SimpleNamespace
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.reminders.application.rule_service import ReminderRulesService
from src.modules.reminders.application.service import RemindersService
from src.modules.reminders.domain.value_objects.reminder_rules import (
    REPEATABLE_RULES,
    RULE_DEFAULTS,
    VARIABLE_LABELS,
    RuleType,
    effective_template,
)
from src.modules.reminders.domain.value_objects.reminder_status import ReminderStatus
from src.modules.reminders.domain.value_objects.reminder_target import ReminderTargetType
from src.modules.reminders.schemas.request import (
    CreateReminderRequest,
    ReminderRuleUpdate,
    UpdateReminderRequest,
)
from src.modules.reminders.schemas.response import (
    ReminderDeliveryResponse,
    ReminderResponse,
    ReminderRuleResponse,
    ReminderTemplateVariable,
)
from src.shared.dependencies.auth import CurrentUserId
from src.shared.responses.response import ApiResponse

router = APIRouter()

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


class MsgResp(BaseModel):
    detail: str


@router.post("", response_model=ApiResponse[ReminderResponse], status_code=201)
async def create_reminder(
    payload: CreateReminderRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ReminderResponse]:
    reminder = await RemindersService(db=db).create(user_id, payload)
    return ApiResponse.created(ReminderResponse.model_validate(reminder))


class ReminderImageResponse(BaseModel):
    """Ảnh vừa tải lên, chờ gắn vào lời nhắc."""

    key: str
    filename: str
    content_type: str


@router.post(
    "/attachments",
    response_model=ApiResponse[ReminderImageResponse],
    status_code=201,
    summary="Tải ảnh để chèn vào thư nhắc",
)
async def upload_reminder_image(
    user_id: CurrentUserId,
    db: DBSession,
    file: UploadFile = File(...),
) -> ApiResponse[ReminderImageResponse]:
    """Nhận MỘT ảnh, cất vào kho, trả khoá để gắn vào lời nhắc khi lưu.

    Chỉ nhận ẢNH: email không phát được video, còn tệp tài liệu thì trình đọc mail hiện
    thành cục tải về chứ không hiện trong thân thư — mà mục đích ở đây là để khách NHÌN
    THẤY ngay (nhất là mã QR chuyển khoản).  #Huynh
    """
    from src.infrastructure.storage.object_storage import object_storage, resolve_content_type
    from src.modules.reminders.application.attachments import validate_image

    data = await file.read()
    filename = file.filename or "image.png"
    content_type = resolve_content_type(file.content_type or "", filename)
    validate_image(content_type=content_type, data=data)

    key = await object_storage.upload(
        data=data,
        content_type=content_type,
        prefix=f"reminders/{user_id}",
        filename=filename,
    )
    return ApiResponse.created(
        ReminderImageResponse(key=key, filename=filename, content_type=content_type)
    )


class ReminderPreviewRequest(BaseModel):
    """Bản nháp lời nhắc để dựng thử thư — KHÔNG lưu gì."""

    reminder_type: str
    target_type: str
    target_id: uuid.UUID
    message: str
    attachments: list[dict[str, str]] = []


class ReminderPreviewResponse(BaseModel):
    subject: str
    html: str
    recipient: str | None = None


@router.post("/preview", response_model=ApiResponse[ReminderPreviewResponse])
async def preview_reminder(
    payload: ReminderPreviewRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ReminderPreviewResponse]:
    """Dựng ĐÚNG lá thư khách sẽ nhận, không gửi và không lưu gì.

    Vì sao phải để server dựng thay vì frontend tự vẽ: thư nhắc thanh toán nay có mã QR và
    số tài khoản. Frontend dựng lại một bản "gần giống" thì sớm muộn cũng lệch với thư thật
    — mà lệch ở đây nghĩa là freelancer duyệt một đằng, khách nhận một nẻo, và tiền có thể
    chuyển nhầm chỗ. Đúng bài học từ màn báo giá: một nguồn dựng duy nhất.

    Khác đường gửi thật đúng MỘT chỗ: mã QR nhúng thẳng bằng `data:` để trình duyệt hiện
    được, còn thư thật đính kèm ảnh dạng `cid:` (Gmail cắt bỏ `data:`).  #Huynh
    """
    import base64

    from src.modules.reminders.application.delivery_service import build_body, build_subject
    from src.modules.reminders.application.payment_block import build_payment_section
    from src.modules.reminders.infrastructure.repository import RemindersRepository

    repo = RemindersRepository(db)
    client, label = await repo.resolve_target(
        target_type=payload.target_type,
        target_id=payload.target_id,
        owner_user_id=user_id,
    )
    owner = await repo.get_owner(user_id)

    draft = SimpleNamespace(
        reminder_type=payload.reminder_type,
        target_type=payload.target_type,
        target_id=payload.target_id,
        owner_user_id=user_id,
    )
    payment_html, payment_plain, qr_png = await build_payment_section(db, draft, owner, label)
    if qr_png is not None:
        payment_html = payment_html.replace(
            "cid:vietqr",
            "data:image/png;base64," + base64.b64encode(qr_png).decode(),
        )

    # Ảnh freelancer chèn: bản xem trước dùng `data:` để trình duyệt hiện được; thư thật thì
    # đính kèm dạng `cid:` (Gmail cắt bỏ `data:`).
    from src.infrastructure.storage.object_storage import object_storage
    from src.modules.reminders.application.attachments import (
        images_html,
        load_image_bytes,
        parse_attachments,
    )

    images = parse_attachments(payload.attachments)
    loaded = await load_image_bytes(object_storage, images)
    srcs = {
        cid: f"data:image/png;base64,{base64.b64encode(raw).decode()}"
        for cid, raw in loaded.items()
    }
    payment_html = images_html(images, srcs) + payment_html

    html, _ = build_body(
        payload.message,
        owner.full_name if owner else None,
        owner.email if owner else None,
        label,
        payment_html=payment_html,
        payment_plain=payment_plain,
    )
    return ApiResponse.ok(
        ReminderPreviewResponse(
            subject=build_subject(payload.reminder_type, label),
            html=html,
            recipient=(client.email if client else None),
        )
    )


@router.get("", response_model=ApiResponse[list[ReminderResponse]])
async def list_reminders(
    user_id: CurrentUserId,
    db: DBSession,
    status: ReminderStatus | None = Query(
        default=None, description="Filter by status: pending, sent, failed, cancelled, skipped"
    ),
    target_type: ReminderTargetType | None = Query(
        default=None, description="Filter by target type: deal, client, invoice, contract"
    ),
) -> ApiResponse[list[ReminderResponse]]:
    reminders = await RemindersService(db=db).list_all(
        user_id, status=status, target_type=target_type
    )
    return ApiResponse.ok([ReminderResponse.model_validate(r) for r in reminders])


# ĐẶT TRƯỚC `/{reminder_id}` — FastAPI khớp route theo thứ tự khai báo, để sau thì
# "/reminders/rules" bị nuốt vào route động và trả 422 vì "rules" không phải UUID.  #Huynh
@router.get("/rules", response_model=ApiResponse[list[ReminderRuleResponse]])
async def list_reminder_rules(
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[list[ReminderRuleResponse]]:
    """Năm quy tắc nhắc tự động. Lần gọi đầu tiên tự tạo bộ mặc định."""
    rules = await ReminderRulesService(db=db).list_for_user(user_id)
    return ApiResponse.ok([_rule_response(rule) for rule in rules])


@router.patch("/rules/{rule_type}", response_model=ApiResponse[ReminderRuleResponse])
async def update_reminder_rule(
    rule_type: str,
    payload: ReminderRuleUpdate,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ReminderRuleResponse]:
    rule = await ReminderRulesService(db=db).update(
        user_id, rule_type, **payload.model_dump(exclude_unset=True)
    )
    return ApiResponse.ok(_rule_response(rule))


def _rule_response(rule: Any) -> ReminderRuleResponse:
    rule_type = RuleType(rule.rule_type)
    spec = RULE_DEFAULTS.get(rule_type)
    return ReminderRuleResponse(
        rule_type=rule.rule_type,
        is_enabled=rule.is_enabled,
        offset_days=rule.offset_days,
        repeat_every_days=rule.repeat_every_days,
        channel=rule.channel,
        auto_send=rule.auto_send,
        send_at_hour=rule.send_at_hour,
        label=spec.label if spec else "",
        supports_repeat=rule_type in REPEATABLE_RULES,
        message_template=effective_template(rule_type, rule.message_template),
        is_custom_template=bool((rule.message_template or "").strip()),
        template_variables=[
            ReminderTemplateVariable(token="{" + name + "}", label=VARIABLE_LABELS[name])
            for name in (spec.variables if spec else ())
        ],
    )


@router.get("/{reminder_id}", response_model=ApiResponse[ReminderResponse])
async def get_reminder(
    reminder_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ReminderResponse]:
    reminder = await RemindersService(db=db).get_one(user_id, reminder_id)
    return ApiResponse.ok(ReminderResponse.model_validate(reminder))


@router.patch("/{reminder_id}", response_model=ApiResponse[ReminderResponse])
async def update_reminder(
    reminder_id: uuid.UUID,
    payload: UpdateReminderRequest,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ReminderResponse]:
    reminder = await RemindersService(db=db).update(user_id, reminder_id, payload)
    return ApiResponse.ok(ReminderResponse.model_validate(reminder))


@router.post("/{reminder_id}/send", response_model=ApiResponse[ReminderDeliveryResponse])
async def send_reminder_now(
    reminder_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[ReminderDeliveryResponse]:
    """Gửi lời nhắc ngay, không đợi tới giờ đã hẹn."""
    reminder, result = await RemindersService(db=db).send_now(user_id, reminder_id)
    return ApiResponse.ok(
        ReminderDeliveryResponse(
            reminder=ReminderResponse.model_validate(reminder),
            status=result.status,
            detail=result.detail,
            delivered=result.delivered,
        )
    )


@router.delete("/{reminder_id}", response_model=ApiResponse[MsgResp])
async def cancel_reminder(
    reminder_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DBSession,
) -> ApiResponse[MsgResp]:
    await RemindersService(db=db).cancel(user_id, reminder_id)
    return ApiResponse.ok(MsgResp(detail="Reminder cancelled"))
