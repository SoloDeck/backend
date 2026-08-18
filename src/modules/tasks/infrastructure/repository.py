import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import (
    ChecklistItemModel,
    DealModel,
    ProjectModel,
    ReminderModel,
    TaskModel,
)


@dataclass
class TaskRepository:
    db: AsyncSession

    async def entity_exists_for_owner(
        self, entity_type: str, entity_id: uuid.UUID, owner_user_id: uuid.UUID
    ) -> bool:
        """Verify the polymorphic parent entity exists and belongs to the user.

        There is no FK on tasks.entity_id, so tenant isolation is enforced here by
        checking the owning project / deal / reminder.
        """
        if entity_type == "project":
            stmt = select(ProjectModel.id).where(
                ProjectModel.id == entity_id,
                ProjectModel.owner_id == owner_user_id,
            )
        elif entity_type == "deal":
            stmt = select(DealModel.id).where(
                DealModel.id == entity_id,
                DealModel.owner_user_id == owner_user_id,
                DealModel.deleted_at.is_(None),
            )
        elif entity_type == "reminder":
            stmt = select(ReminderModel.id).where(
                ReminderModel.id == entity_id,
                ReminderModel.owner_user_id == owner_user_id,
            )
        else:
            return False
        return await self.db.scalar(stmt) is not None

    async def create(self, **values: object) -> TaskModel:
        task = TaskModel(**values)
        self.db.add(task)
        await self.db.flush()
        await self.db.refresh(task)
        return task

    async def next_position(self, entity_type: str, entity_id: uuid.UUID) -> int:
        """Số thứ tự kế tiếp của entity. Gọi MỘT lần rồi tự cộng dồn khi tạo nhiều task.

        Đừng gọi trong vòng lặp: vừa N truy vấn, vừa không chắc thấy các task vừa `add` mà
        chưa `flush` — hai task cùng lô sẽ nhận trùng số.  #Huynh
        """
        current = await self.db.scalar(
            select(func.max(TaskModel.position)).where(
                TaskModel.entity_type == entity_type,
                TaskModel.entity_id == entity_id,
            )
        )
        return int(current) + 1 if current is not None else 0

    async def count_billing_tasks(
        self, entity_type: str, entity_id: uuid.UUID, legacy_prefix: str
    ) -> tuple[int, int]:
        """(tổng, đã xong) các task THU TIỀN của entity.

        Dùng cho guard "hoàn thành dự án": còn mốc thu tiền chưa tick thì chưa cho đóng deal.

        Dấu nhận biết chính là `billing_amount IS NOT NULL`. Vế `title LIKE 'Thu tiền:%'` là
        LỐI RƠI VỀ DUY NHẤT còn giữ lại sau khi backfill, dành cho các task mà migration cố ý
        bỏ qua (tên đã bị sửa, tổng lệch giá deal). Giữ đúng ở ĐÂY chứ không ở chỗ khác, vì
        đây là chỗ fail-an-toàn: bỏ sót một task ở đây nghĩa là ĐÓNG DEAL KHI CHƯA THU TIỀN —
        hỏng nặng nhất trong sản phẩm này. Các chỗ còn lại (xuất hoá đơn, doanh thu) thì đòi
        `billing_amount` hẳn hoi, để task sót lộ ra chứ không âm thầm bị cộng nửa vời.  #Huynh
        """
        base = (
            TaskModel.entity_type == entity_type,
            TaskModel.entity_id == entity_id,
            or_(
                TaskModel.billing_amount.is_not(None),
                TaskModel.title.startswith(legacy_prefix),
            ),
        )
        total = await self.db.scalar(select(func.count()).select_from(TaskModel).where(*base))
        done = await self.db.scalar(
            select(func.count())
            .select_from(TaskModel)
            .where(*base, TaskModel.status == "done")
        )
        return int(total or 0), int(done or 0)

    async def has_billing_tasks(
        self, entity_type: str, entity_id: uuid.UUID, legacy_prefix: str
    ) -> bool:
        """Entity đã có task thu tiền nào chưa — KHOÁ IDEMPOTENCY của bộ sinh task.

        Vì sao không dedupe theo tên như trước: tên task giờ là nhãn hạng mục, khác hẳn tên
        `"Thu tiền: <mốc>"` của bản cũ. Một deal cũ đã có đủ task theo mốc, khi vào `active`
        hay khi sửa hợp đồng sẽ được sinh THÊM một bộ task theo hạng mục — không tên nào
        trùng nên dedupe theo tên không bắt được, và doanh thu bị cộng đôi.  #Huynh
        """
        found = await self.db.scalar(
            select(TaskModel.id)
            .where(
                TaskModel.entity_type == entity_type,
                TaskModel.entity_id == entity_id,
                or_(
                    TaskModel.billing_amount.is_not(None),
                    TaskModel.title.startswith(legacy_prefix),
                ),
            )
            .limit(1)
        )
        return found is not None

    async def get_by_id(self, task_id: uuid.UUID) -> TaskModel | None:
        return await self.db.scalar(select(TaskModel).where(TaskModel.id == task_id))  # type: ignore[no-any-return]

    async def list_by_entity(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[TaskModel], int]:
        conditions = [
            TaskModel.entity_type == entity_type,
            TaskModel.entity_id == entity_id,
        ]
        if status is not None:
            conditions.append(TaskModel.status == status)

        total = await self.db.scalar(select(func.count()).select_from(TaskModel).where(*conditions))
        # Sắp theo THỨ TỰ HIỂN THỊ, không theo thời điểm tạo.
        #
        # Bản trước là `created_at.desc()` trần. Với task thu tiền — cả lô sinh trong MỘT
        # transaction, mà `now()` của PostgreSQL trả thời điểm bắt đầu transaction — mọi dòng
        # có `created_at` bằng nhau, nên đó là sắp xếp hoà hoàn toàn: thứ tự do planner quyết
        # và đổi giữa các lần gọi. Freelancer kéo sắp lại hạng mục ở báo giá cũng vô nghĩa.
        #
        # `id` là khoá chót để không bao giờ còn hoà — phân trang mà thứ tự đổi giữa hai trang
        # thì có bản ghi hiện hai lần và có bản ghi biến mất.  #Huynh
        result = await self.db.execute(
            select(TaskModel)
            .where(*conditions)
            .order_by(TaskModel.position, TaskModel.created_at, TaskModel.id)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), int(total or 0)

    async def save(self, task: TaskModel) -> TaskModel:
        await self.db.flush()
        await self.db.refresh(task)
        return task

    async def delete(self, task: TaskModel) -> None:
        await self.db.delete(task)
        await self.db.flush()

    # --- checklist items ------------------------------------------------------

    async def add_checklist_item(self, **values: object) -> ChecklistItemModel:
        item = ChecklistItemModel(**values)
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def get_checklist_item(
        self, item_id: uuid.UUID, task_id: uuid.UUID
    ) -> ChecklistItemModel | None:
        res = await self.db.scalar(
            select(ChecklistItemModel).where(
                ChecklistItemModel.id == item_id,
                ChecklistItemModel.task_id == task_id,
            )
        )
        return res

    async def save_checklist_item(self, item: ChecklistItemModel) -> ChecklistItemModel:
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def delete_checklist_item(self, item: ChecklistItemModel) -> None:
        await self.db.delete(item)
        await self.db.flush()
