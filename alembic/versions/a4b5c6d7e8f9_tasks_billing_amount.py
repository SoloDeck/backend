"""tasks.billing_amount — số tiền phải thu, chốt thẳng lên task

Revision ID: a4b5c6d7e8f9
Revises: z3a4b5c6d7e8
Create Date: 2026-08-13 20:40:00.000000

Nghiệp vụ đổi: thu tiền theo HẠNG MỤC CHI PHÍ (mục 7) thay vì mốc thanh toán theo % (mục 8).
Mỗi hạng mục = 1 task = 1 hoá đơn.

Vì sao phải có cột chứ không tính lại được như cũ: bản cũ nhận biết task thu tiền bằng TIỀN TỐ
TÊN `"Thu tiền: "`, rồi tra ngược báo giá đã chốt và khớp mốc VỚI TÊN TASK để ra số tiền.
Freelancer đổi tên task một chữ là đứt cả hai đầu — không xuất được hoá đơn, và bảng doanh thu
âm thầm coi mốc đó chưa thu. Một cột thì không đứt được.

BACKFILL — đây là phần đụng dữ liệu thật, đọc kỹ trước khi chạy:

Mọi task `"Thu tiền: ..."` đang có được tính sẵn số tiền rồi ghi vào cột mới, dùng ĐÚNG phép
chia mà `analytics/application/milestone_money.py` vẫn tính lúc chạy (chia theo %, mốc không
khai % thì chia đều phần còn lại, đồng lẻ dồn vào mốc CUỐI). Tức là "vật chất hoá một phép
tính đã có", không phải nghiệp vụ mới.

Cố ý bảo thủ — CHỈ ghi khi tổng các mốc khớp TUYỆT ĐỐI `deals.estimated_value`. Lệch một đồng,
task bị đổi tên, hay không tìm được báo giá đã chốt thì để NULL. Thà sót vài task (guard đóng
dự án vẫn bắt được nhờ lối rơi về theo tiền tố) còn hơn ghi một con số sai vào chứng từ tiền.

ĐỔI HÀNH VI cần biết: doanh thu của deal cũ từ nay ĐÓNG BĂNG tại thời điểm migrate, không còn
trôi theo `deals.estimated_value` nữa. Đúng hơn về mặt nghiệp vụ (giá đã ký thì không nên trôi),
nhưng vẫn là một thay đổi.

Phép chia được CHÉP INLINE, không `import src.` — migration phải đóng băng theo thời gian, còn
`milestone_money.py` thì sẽ đổi ngay trong chính đợt này.
"""

import json
from collections.abc import Sequence
from decimal import Decimal

import sqlalchemy as sa

from alembic import op

revision: str = "a4b5c6d7e8f9"
down_revision: str | None = "z3a4b5c6d7e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Tiền tố task thu tiền của bản cũ. Đóng băng ở đây kể cả khi hằng số bên `src` đổi tên.
_LEGACY_PREFIX = "Thu tiền:"

# Lịch chuẩn khi báo giá không nêu mốc nào — trùng `default_payment_milestones()` lúc viết bản này.
_DEFAULT_MILESTONES: list[tuple[str, int | None]] = [
    ("Đặt cọc khi ký hợp đồng", 50),
    ("Thanh toán khi nghiệm thu & bàn giao", 50),
]


def _milestones_from_content(content: object) -> list[tuple[str, int | None]]:
    """(nhãn, %) của từng đợt. Chép theo `pdf_content.extract_payment_milestones`, rút gọn
    còn đúng hai trường mà phép chia cần."""
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except (ValueError, TypeError):
            return []
    if not isinstance(content, dict):
        return []

    raw = content.get("payment_milestones")
    if raw is None:
        terms = content.get("terms")
        if isinstance(terms, dict):
            raw = terms.get("payment_schedule") or terms.get("payment_milestones")
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []

    out: list[tuple[str, int | None]] = []
    for entry in raw:
        if isinstance(entry, str):
            if entry.strip():
                out.append((entry.strip(), None))
            continue
        if not isinstance(entry, dict):
            continue
        label = (
            entry.get("label")
            or entry.get("description")
            or entry.get("name")
            or entry.get("stage")
        )
        label = str(label).strip() if label is not None else ""
        if not label:
            continue
        raw_percent = entry.get("percent", entry.get("percentage"))
        try:
            percent = (
                int(float(str(raw_percent).strip().rstrip("%")))
                if raw_percent not in (None, "")
                else None
            )
        except (TypeError, ValueError):
            percent = None
        out.append((label, percent))
    return out


def _split(milestones: list[tuple[str, int | None]], total: Decimal) -> list[Decimal]:
    """Chia `total` theo %. Chép `milestone_money.split_milestone_amounts` nguyên văn logic."""
    if not milestones or total <= 0:
        return [Decimal(0) for _ in milestones]

    percents = [p for _, p in milestones]
    known = sum(p for p in percents if p is not None)
    missing = [i for i, p in enumerate(percents) if p is None]
    share_for_missing = (
        max(Decimal(0), Decimal(100) - Decimal(known)) / len(missing) if missing else Decimal(0)
    )

    amounts: list[Decimal] = []
    for percent in percents:
        ratio = Decimal(percent) if percent is not None else share_for_missing
        amounts.append((total * ratio / Decimal(100)).quantize(Decimal("1")))

    total_percent = Decimal(known) + share_for_missing * len(missing)
    if total_percent == 100:
        amounts[-1] += total - sum(amounts)
    return amounts


def _backfill(bind: sa.engine.Connection) -> None:
    rows = bind.execute(
        sa.text(
            """
            SELECT t.id            AS task_id,
                   t.title         AS title,
                   d.id            AS deal_id,
                   d.estimated_value AS estimated_value,
                   pr.content      AS content
            FROM tasks t
            JOIN projects p ON p.id = t.entity_id AND t.entity_type = 'project'
            JOIN deals d    ON d.id = p.deal_id
            LEFT JOIN LATERAL (
                SELECT content
                FROM proposals
                WHERE deal_id = d.id AND status = 'accepted'
                ORDER BY version_number DESC
                LIMIT 1
            ) pr ON TRUE
            WHERE t.title LIKE :prefix
            """
        ),
        {"prefix": f"{_LEGACY_PREFIX}%"},
    ).mappings().all()

    # Gom theo deal: điều kiện "tổng khớp tuyệt đối" chỉ xét được khi có đủ mốc của một deal.
    by_deal: dict[object, list[dict]] = {}
    for row in rows:
        by_deal.setdefault(row["deal_id"], []).append(dict(row))

    updates: list[dict] = []
    for deal_rows in by_deal.values():
        total = Decimal(deal_rows[0]["estimated_value"] or 0)
        if total <= 0:
            continue

        milestones = _milestones_from_content(deal_rows[0]["content"]) or _DEFAULT_MILESTONES
        amounts = _split(milestones, total)

        # Khớp task ↔ mốc bằng ĐÚNG tên mà bản cũ sinh ra.
        by_title = {
            f"{_LEGACY_PREFIX} {label}"[:500]: amount
            for (label, _), amount in zip(milestones, amounts, strict=True)
        }

        matched = [
            {"task_id": r["task_id"], "amount": by_title[r["title"]]}
            for r in deal_rows
            if r["title"] in by_title
        ]
        # Thiếu một task, thừa một task, hay tổng lệch → bỏ qua CẢ deal. Ghi một nửa còn tệ
        # hơn không ghi: bảng doanh thu sẽ cộng ra một con số trông có vẻ đúng.
        if len(matched) != len(by_title):
            continue
        if sum(m["amount"] for m in matched) != total:
            continue
        updates.extend(matched)

    if updates:
        bind.execute(
            sa.text("UPDATE tasks SET billing_amount = :amount WHERE id = :task_id"), updates
        )


def upgrade() -> None:
    op.add_column("tasks", sa.Column("billing_amount", sa.Numeric(15, 2), nullable=True))
    op.create_check_constraint(
        "ck_tasks_billing_amount_non_negative",
        "tasks",
        "billing_amount IS NULL OR billing_amount >= 0",
    )
    # Chỉ mục PHẦN theo ENTITY trước: hai truy vấn dùng nó (guard đóng dự án, bảng doanh thu)
    # đều lọc theo entity rồi mới tới cờ thu tiền.
    op.create_index(
        "idx_tasks_billing",
        "tasks",
        ["entity_type", "entity_id"],
        postgresql_where=sa.text("billing_amount IS NOT NULL"),
    )
    _backfill(op.get_bind())


def downgrade() -> None:
    op.drop_index("idx_tasks_billing", table_name="tasks")
    op.drop_constraint("ck_tasks_billing_amount_non_negative", "tasks", type_="check")
    op.drop_column("tasks", "billing_amount")
