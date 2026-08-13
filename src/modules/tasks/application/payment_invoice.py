"""Xuất hóa đơn cho một task THU TIỀN (task có `billing_amount`).

Đặt ở module riêng chứ không nhét vào `TaskService`: việc này cần đọc deal, khách hàng và
service hóa đơn — kéo cả ba vào `TaskService` là biến một service CRUD thành nút giao của
nửa hệ thống.

**Số tiền do SERVER quyết, không nhận từ client.** Frontend gửi lên số tiền thì có hai chỗ
tính tiền, và chỉ cần một lần lệch là hóa đơn gửi khách khác bảng doanh thu.

Số tiền lấy thẳng từ `tasks.billing_amount` — con số đã chốt lúc sinh task từ hạng mục chi
phí của báo giá đã chốt. Bản cũ tra ngược báo giá rồi chia lại % và khớp mốc VỚI TÊN TASK;
đổi tên task một chữ là không xuất được hóa đơn, mà lỗi chỉ hiện ra đúng lúc freelancer định
đi đòi tiền.  #Huynh
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.exceptions.domain import BusinessRuleError, NotFoundError

# Hạn thanh toán mặc định khi xuất hóa đơn từ một mốc.
#
# Mốc thanh toán của báo giá chỉ ghi ĐIỀU KIỆN bằng văn xuôi ("Khi ký hợp đồng", "Khi nghiệm
# thu & bàn giao") chứ không có ngày cụ thể — không có gì để suy ra một ngày. 14 ngày là mức
# quen thuộc với khách doanh nghiệp Việt Nam, và freelancer sửa lại được trước khi gửi.
DEFAULT_DUE_DAYS = 14


async def create_invoice_for_payment_task(
    db: AsyncSession,
    task_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    *,
    due_date: date | None = None,
):
    """Tạo (hoặc trả về) hóa đơn của một task "Thu tiền:".

    Task đã có hóa đơn thì **trả về đúng hóa đơn đó, không tạo cái thứ hai** — nút này nằm
    trong hộp thoại xác nhận nên bấm hai lần là chuyện chắc chắn xảy ra, và hai hóa đơn cho
    cùng một mốc thì khách trả tiền hai lần hoặc không trả lần nào.
    """
    from src.infrastructure.database.models import ProjectModel
    from src.modules.invoices.application.service import InvoicesService
    from src.modules.invoices.infrastructure.repository import InvoicesRepository
    from src.modules.invoices.schemas.request import InvoiceLineItemRequest, InvoiceRequest
    from src.modules.tasks.application.service import TaskService

    task_service = TaskService(db)
    task = await task_service._get_owned_task(task_id, owner_user_id)

    # Số tiền nằm NGAY TRÊN TASK. Bản cũ phải tra ngược báo giá đã chốt, chia lại % rồi khớp
    # mốc với TÊN TASK — đổi tên task một chữ là hỏng, và lỗi hiện ra đúng lúc freelancer định
    # đi đòi tiền. Giờ không còn gì để đứt.
    #
    # Đòi `billing_amount` hẳn hoi chứ không rơi về tiền tố tên: task cũ mà migration
    # `a4b5c6d7e8f9` cố ý bỏ qua (tên đã sửa, tổng lệch giá deal) thì phải LỘ RA ở đây, chứ
    # không được lặng lẽ xuất một hoá đơn dựng từ con số đoán.  #Huynh
    if task.billing_amount is None:
        raise BusinessRuleError(
            "Chỉ xuất hóa đơn được cho công việc thu tiền do hệ thống tạo từ hạng mục chi phí "
            "của báo giá đã chốt."
        )

    invoices_repo = InvoicesRepository(db)
    if task.invoice_id is not None:
        existing = await invoices_repo.get_by_id(task.invoice_id, owner_user_id)
        if existing is not None:
            return existing
        # Hóa đơn đã bị xóa (FK là SET NULL nên cột lẽ ra đã NULL). Rơi xuống tạo mới thay vì
        # nổ: task vẫn còn đó và tiền vẫn phải thu.

    if task.entity_type != "project":
        raise BusinessRuleError("Công việc thu tiền phải nằm trên một dự án.")

    project = await db.get(ProjectModel, task.entity_id)
    if project is None or project.deal_id is None:
        raise BusinessRuleError("Dự án của công việc này chưa gắn với deal nào.")

    deal = await invoices_repo.get_deal_by_id(project.deal_id, owner_user_id)
    if deal is None:
        raise NotFoundError(f"Deal {project.deal_id} not found")

    if task.billing_amount <= 0:
        raise BusinessRuleError("Hạng mục này đang là 0 đồng — chốt số tiền cho nó trước đã.")

    invoice = await InvoicesService(db=db, repo=invoices_repo).create(
        owner_user_id,
        InvoiceRequest(
            client_id=deal.client_id,
            deal_id=deal.id,
            due_date=due_date or date.today() + timedelta(days=DEFAULT_DUE_DAYS),
            line_items=[
                InvoiceLineItemRequest(
                    description=task.title,
                    quantity=Decimal(1),
                    unit_price=task.billing_amount,
                )
            ],
        ),
    )

    task.invoice_id = invoice.id
    await task_service.repo.save(task)
    return invoice
