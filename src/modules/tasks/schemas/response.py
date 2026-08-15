import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from src.modules.tasks.domain.value_objects.priority import Priority
from src.modules.tasks.domain.value_objects.task_owner import TaskOwner
from src.modules.tasks.domain.value_objects.task_status import TaskStatus


class ChecklistItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    text: str
    is_done: bool
    position: int


class TaskInvoiceSummary(BaseModel):
    """Đủ để màn Công việc vẽ nhãn trạng thái mà không phải gọi thêm một vòng API.

    Cố ý KHÔNG trả cả hóa đơn: hàng task chỉ cần biết "đã gửi chưa, thu được chưa, bao
    nhiêu". Trả nguyên chứng từ vào danh sách task là kéo theo cả hạng mục, thuế, lịch sử
    thanh toán cho một chỗ chỉ hiện đúng một dòng chữ.  #Huynh
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str
    status: str
    total: Decimal
    amount_paid: Decimal


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: TaskOwner
    entity_id: uuid.UUID
    title: str
    description: str | None
    priority: Priority
    status: TaskStatus
    deadline: datetime | None
    checklist_items: list[ChecklistItemResponse] = []
    # Số tiền phải thu. KHÔNG NULL = đây là task THU TIỀN — frontend dựa vào đúng cột này để
    # vẽ nút hóa đơn và để đếm mốc chưa thu, thay cho việc dò tiền tố tên như trước.
    #
    # Chỉ ĐỌC: không có trong body tạo/sửa task. Cho client tự đặt số tiền là cho phép đúc ra
    # một task thu tiền số tuỳ ý rồi xuất hóa đơn gửi khách bằng con số đó.  #Huynh
    billing_amount: Decimal | None = None
    # `on_signing` = đòi được NGAY; `on_completion` = đòi khi công việc xong. `None` với task
    # cũ / task freelancer tự thêm. Frontend dùng để vẽ nhãn "Thu ngay" và để hỏi lại khi xuất
    # hóa đơn cho việc chưa tick xong. Chỉ ĐỌC, y như `billing_amount`.  #Huynh
    billing_due_type: str | None = None
    # Chỉ có với task thu tiền ĐÃ xuất hóa đơn. `None` nghĩa là chưa xuất — frontend hiện
    # nút "Tạo & gửi hóa đơn", còn có rồi thì hiện nhãn theo `invoice.status`.
    invoice: TaskInvoiceSummary | None = None
    created_at: datetime
    updated_at: datetime
