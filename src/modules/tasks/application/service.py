"""Tasks application service.

One service backs every polymorphic entry point (/projects/.../tasks,
/deals/.../tasks, /reminders/.../tasks). Tasks have no owner column of their own;
tenant isolation is enforced by verifying the owning entity belongs to the user
before any read or write (see TaskRepository.entity_exists_for_owner).
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import ChecklistItemModel, TaskModel
from src.modules.tasks.infrastructure.repository import TaskRepository
from src.modules.tasks.schemas.request import (
    CreateChecklistItemRequest,
    CreateTaskRequest,
    UpdateChecklistItemRequest,
    UpdateTaskRequest,
)
from src.shared.exceptions.domain import BusinessRuleError, NotFoundError

_DEFAULT_PRIORITY = "medium"

# Tiền tố tên của TASK THU TIỀN bản CŨ (sinh từ mốc thanh toán theo %).
#
# Không còn là dấu nhận biết nữa — `tasks.billing_amount IS NOT NULL` mới là. Giữ lại đúng
# một vai trò: lối rơi về cho các task mà migration `a4b5c6d7e8f9` cố ý không backfill (tên
# đã bị sửa, tổng lệch giá deal), để guard "hoàn thành dự án" vẫn chặn được. Xem
# `TaskRepository.count_billing_tasks`.  #Huynh
PAYMENT_TASK_PREFIX = "Thu tiền:"


@dataclass(frozen=True)
class BillingTaskPayload:
    """Một task THU TIỀN do hệ thống sinh — nội bộ, KHÔNG phải shape API.

    Cố ý không dùng `CreateTaskRequest`: đó là body công khai của `POST /projects/{id}/tasks`,
    thêm `billing_amount` vào đó là cho phép client bất kỳ tự đúc ra task thu tiền với số tiền
    tuỳ ý, rồi xuất hoá đơn gửi khách bằng con số đó.  #Huynh
    """

    title: str
    amount: Decimal
    description: str | None = None
    # `on_signing` / `on_completion`, chép từ hạng mục chi phí. `None` = lối rơi về cho báo
    # giá cũ theo mốc %, khi không suy được thời điểm thu.
    due_type: str | None = None


@dataclass
class TaskService:
    db: AsyncSession
    repo: TaskRepository = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.repo is None:
            self.repo = TaskRepository(self.db)

    async def _require_entity_owner(
        self, entity_type: str, entity_id: uuid.UUID, owner_user_id: uuid.UUID
    ) -> None:
        if not await self.repo.entity_exists_for_owner(entity_type, entity_id, owner_user_id):
            raise NotFoundError(f"{entity_type.capitalize()} {entity_id} not found")

    async def _get_owned_task(self, task_id: uuid.UUID, owner_user_id: uuid.UUID) -> TaskModel:
        task = await self.repo.get_by_id(task_id)
        if task is None:
            raise NotFoundError(f"Task {task_id} not found")
        await self._require_entity_owner(task.entity_type, task.entity_id, owner_user_id)
        return task

    # --- tasks ----------------------------------------------------------------

    async def list_by_entity(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[TaskModel], int]:
        await self._require_entity_owner(entity_type, entity_id, owner_user_id)
        offset = (page - 1) * page_size
        return await self.repo.list_by_entity(
            entity_type, entity_id, status=status, offset=offset, limit=page_size
        )

    async def create_for_entity(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        payload: CreateTaskRequest,
    ) -> TaskModel:
        await self._require_entity_owner(entity_type, entity_id, owner_user_id)
        return await self.repo.create(
            entity_type=entity_type,
            entity_id=entity_id,
            title=payload.title,
            description=payload.description,
            priority=payload.priority.value if payload.priority else _DEFAULT_PRIORITY,
            deadline=payload.deadline,
        )

    async def create_many_for_entity(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        payloads: list[CreateTaskRequest],
        *,
        skip_existing_titles: bool = True,
    ) -> list[TaskModel]:
        """Tạo NHIỀU task một lượt cho cùng một entity — dùng cho việc SINH TỰ ĐỘNG.

        `skip_existing_titles` (mặc định) bỏ qua các title đã có sẵn trên entity, nên gọi
        lại nhiều lần cũng KHÔNG nhân đôi (idempotent) — cần thiết vì một deal có thể có
        nhiều báo giá được chốt. Chủ sở hữu entity chỉ kiểm MỘT lần cho cả lô.  #Huynh
        """
        await self._require_entity_owner(entity_type, entity_id, owner_user_id)
        seen: set[str] = set()
        if skip_existing_titles:
            rows, _ = await self.repo.list_by_entity(
                entity_type, entity_id, status=None, offset=0, limit=1000
            )
            seen = {row.title for row in rows}
        created: list[TaskModel] = []
        for payload in payloads:
            if payload.title in seen:
                continue
            task = await self.repo.create(
                entity_type=entity_type,
                entity_id=entity_id,
                title=payload.title,
                description=payload.description,
                priority=payload.priority.value if payload.priority else _DEFAULT_PRIORITY,
                deadline=payload.deadline,
            )
            created.append(task)
            seen.add(payload.title)
        return created

    async def create_billing_tasks_for_entity(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        payloads: list[BillingTaskPayload],
    ) -> list[TaskModel]:
        """Sinh các task THU TIỀN cho một entity. Idempotent theo "entity đã có task thu tiền
        chưa", KHÔNG theo tên.

        Vì sao không đi qua `create_many_for_entity`: hàm đó bỏ qua title đã tồn tại. Tên task
        giờ là NHÃN HẠNG MỤC, nên (a) một task thường trùng tên hạng mục sẽ nuốt mất task thu
        tiền — mất tiền khỏi guard và khỏi bảng doanh thu, im lặng; và (b) deal cũ đã có task
        `"Thu tiền: ..."` sẽ được sinh THÊM một bộ mới vì không tên nào trùng → cộng đôi doanh
        thu. Khoá theo "đã có chưa" chặn được cả hai.  #Huynh
        """
        await self._require_entity_owner(entity_type, entity_id, owner_user_id)
        if await self.repo.has_billing_tasks(entity_type, entity_id, PAYMENT_TASK_PREFIX):
            return []

        created: list[TaskModel] = []
        for payload in payloads:
            task = await self.repo.create(
                entity_type=entity_type,
                entity_id=entity_id,
                title=payload.title,
                description=payload.description,
                priority=_DEFAULT_PRIORITY,
                billing_amount=payload.amount,
                billing_due_type=payload.due_type,
            )
            created.append(task)
        return created

    async def payment_task_progress(
        self, entity_type: str, entity_id: uuid.UUID, owner_user_id: uuid.UUID
    ) -> tuple[int, int]:
        """(tổng, đã xong) các task THU TIỀN của entity.

        Guard "hoàn thành dự án" của deals gọi hàm này: còn mốc thu tiền chưa xong thì
        chưa cho đóng deal.  #Huynh
        """
        await self._require_entity_owner(entity_type, entity_id, owner_user_id)
        return await self.repo.count_billing_tasks(entity_type, entity_id, PAYMENT_TASK_PREFIX)

    async def get(self, task_id: uuid.UUID, owner_user_id: uuid.UUID) -> TaskModel:
        return await self._get_owned_task(task_id, owner_user_id)

    async def update(
        self, task_id: uuid.UUID, owner_user_id: uuid.UUID, payload: UpdateTaskRequest
    ) -> TaskModel:
        task = await self._get_owned_task(task_id, owner_user_id)
        data = payload.model_dump(exclude_unset=True)
        for field, value in data.items():
            setattr(task, field, value)
        return await self.repo.save(task)

    async def delete(self, task_id: uuid.UUID, owner_user_id: uuid.UUID) -> None:
        task = await self._get_owned_task(task_id, owner_user_id)
        # Task thu tiền là một KHOẢN PHẢI THU, không phải một việc vặt tự thêm. Xoá nó là mất
        # khoản đó khỏi guard "hoàn thành dự án" lẫn bảng doanh thu, và deal đóng lại được
        # trong khi tiền chưa về. Trước đây không chặn được vì không có gì phân biệt; giờ có
        # `billing_amount` thì chặn được đúng chỗ.
        #
        # Muốn bỏ một khoản thu thì sửa hạng mục chi phí trên báo giá (hoặc lập phụ lục), chứ
        # không phải xoá dòng trên bảng việc.  #Huynh
        if task.billing_amount is not None:
            raise BusinessRuleError(
                "Không xoá được công việc thu tiền — đây là một khoản phải thu của dự án. "
                "Hãy sửa hạng mục chi phí trên báo giá nếu muốn bỏ khoản này."
            )
        await self.repo.delete(task)

    # --- checklist items ------------------------------------------------------

    async def add_checklist_item(
        self,
        task_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        payload: CreateChecklistItemRequest,
    ) -> ChecklistItemModel:
        await self._get_owned_task(task_id, owner_user_id)
        return await self.repo.add_checklist_item(
            task_id=task_id,
            text=payload.text,
            position=payload.position,
        )

    async def update_checklist_item(
        self,
        task_id: uuid.UUID,
        item_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        payload: UpdateChecklistItemRequest,
    ) -> ChecklistItemModel:
        await self._get_owned_task(task_id, owner_user_id)
        item = await self.repo.get_checklist_item(item_id, task_id)
        if item is None:
            raise NotFoundError(f"Checklist item {item_id} not found")
        data = payload.model_dump(exclude_unset=True)
        for field, value in data.items():
            setattr(item, field, value)
        return await self.repo.save_checklist_item(item)

    async def delete_checklist_item(
        self, task_id: uuid.UUID, item_id: uuid.UUID, owner_user_id: uuid.UUID
    ) -> None:
        await self._get_owned_task(task_id, owner_user_id)
        item = await self.repo.get_checklist_item(item_id, task_id)
        if item is None:
            raise NotFoundError(f"Checklist item {item_id} not found")
        await self.repo.delete_checklist_item(item)
