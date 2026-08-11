"""Xuất hóa đơn cho một task "Thu tiền:".

Đặt ở module riêng chứ không nhét vào `TaskService`: việc này cần đọc báo giá đã chốt, bộ
tính tiền của analytics và service hóa đơn — kéo cả ba vào `TaskService` là biến một service
CRUD thành nút giao của nửa hệ thống.

**Số tiền do SERVER tính, không nhận từ client.** Frontend gửi lên số tiền thì có hai chỗ
tính tiền, và chỉ cần một lần lệch là hóa đơn gửi khách khác bảng doanh thu.  #Huynh
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
    from src.ai.proposal_generator.schemas.proposal_document import default_payment_milestones
    from src.infrastructure.database.models import ProjectModel
    from src.modules.analytics.application.milestone_money import (
        milestone_money_for_deal,
        task_title_for,
    )
    from src.modules.invoices.application.service import InvoicesService
    from src.modules.invoices.infrastructure.repository import InvoicesRepository
    from src.modules.invoices.schemas.request import InvoiceLineItemRequest, InvoiceRequest
    from src.modules.proposals.application.pdf_content import extract_payment_milestones
    from src.modules.proposals.infrastructure.repository import ProposalsRepository
    from src.modules.tasks.application.service import PAYMENT_TASK_PREFIX, TaskService

    task_service = TaskService(db)
    task = await task_service._get_owned_task(task_id, owner_user_id)

    if not task.title.startswith(PAYMENT_TASK_PREFIX):
        raise BusinessRuleError(
            "Chỉ xuất hóa đơn được cho công việc thu tiền do hệ thống tạo từ mốc thanh toán "
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

    proposal = await ProposalsRepository(db).get_accepted_by_deal(deal.id, owner_user_id)
    if proposal is None:
        raise BusinessRuleError(
            "Deal chưa có báo giá nào được chốt nên chưa biết mốc này là bao nhiêu tiền."
        )

    milestones = extract_payment_milestones(proposal.content or {}) or default_payment_milestones()
    # Dùng ĐÚNG bộ tính tiền của bảng doanh thu: tổng các hóa đơn sinh ra từ đây luôn khớp
    # tuyệt đối với giá đã chốt, kể cả phần đồng lẻ do làm tròn (dồn vào mốc cuối).
    # `estimated_value` chứ không phải `actual_value`: đây là ĐÚNG trường mà bảng doanh thu
    # dùng làm giá chốt (`analytics/infrastructure/repository.py` — `"final_price":
    # estimated_value`). Lấy trường khác là hóa đơn gửi khách và bảng doanh thu kể hai câu
    # chuyện khác nhau về cùng một deal.
    #
    # (Hai trường này đang lẫn lộn trong toàn dự án: `actual_value` có mặt trong model và
    # API nhưng không nơi nào tự điền, còn analytics thì gọi `estimated_value` là "giá chốt".
    # Cần dọn, nhưng dọn ở đây là đổi ngầm ý nghĩa số liệu — để thành việc riêng.)  #Huynh
    money = milestone_money_for_deal(
        final_price=deal.estimated_value,
        milestones=milestones,
        done_task_titles=set(),
    )

    match = next((m for m in money if task_title_for(m.label) == task.title), None)
    if match is None:
        raise BusinessRuleError(
            f"Không tìm thấy mốc thanh toán ứng với công việc '{task.title}' trong báo giá "
            "đã chốt. Công việc có thể đã bị đổi tên."
        )
    if match.amount <= 0:
        raise BusinessRuleError("Mốc này đang là 0 đồng — chốt giá cho deal trước đã.")

    invoice = await InvoicesService(db=db, repo=invoices_repo).create(
        owner_user_id,
        InvoiceRequest(
            client_id=deal.client_id,
            deal_id=deal.id,
            due_date=due_date or date.today() + timedelta(days=DEFAULT_DUE_DAYS),
            line_items=[
                InvoiceLineItemRequest(
                    description=match.label,
                    quantity=Decimal(1),
                    unit_price=match.amount,
                )
            ],
        ),
    )

    task.invoice_id = invoice.id
    await task_service.repo.save(task)
    return invoice
