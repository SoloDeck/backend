"""them 4 loai billing event cho tien lech, va cho phep su kien khong gan voi user nao

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-09-12 00:00:00.000000

Bon loai su kien moi, deu sinh ra tu mot su that: SePay bat khach GO TAY so tien va noi
dung chuyen khoan, nen lech la chuyen thuong ngay, khac han MoMo/ZaloPay noi cong ep dung
so. Truoc day moi ca lech deu bi gop vao mot nhanh "danh dau that bai", con tien thi da
vao tai khoan that.

  overpayment_received      khach tra thua (go 200.000 thay vi 199.000). Nay VAN kich hoat
                            goi, phan du ghi lai de hoan sau.
  underpayment_received     khach tra thieu. Khong kich hoat, nhung don giu `pending` chu
                            khong `failed`, de lan chuyen bu sau con khop duoc.
  duplicate_payment_received khach quet lai dung ma QR va chuyen them lan nua. Truoc day bi
                            ack im lang nhu "cong gui lai" — tien bien mat khong dau vet.
  unmatched_transfer        tien vao tai khoan nhung khong doc duoc ma don (khach go sai
                            noi dung, hoac ngan hang cat bot). Truoc day tra 404 va khong
                            ghi gi ca.

Kem theo: `billing_events.user_id` va `subscription_id` chuyen sang NULLABLE. Chi rieng
`unmatched_transfer` can dieu nay — dung dinh nghia cua no la khoan tien CHUA biet cua ai.
Moi loai su kien con lai van luon ghi du hai cot.

Vi sao `ADD VALUE IF NOT EXISTS` chay duoc trong transaction cua alembic: PostgreSQL 12 tro
len cho phep, mien la gia tri moi khong duoc DUNG ngay trong cung transaction do. Migration
nay khong chen dong nao nen an toan. Lam y het migration a1b2c3d4e5f6 da them 'zalopay'.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: str | Sequence[str] | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LOAI_MOI = (
    "overpayment_received",
    "underpayment_received",
    "duplicate_payment_received",
    "unmatched_transfer",
)


def upgrade() -> None:
    for loai in LOAI_MOI:
        op.execute(f"ALTER TYPE billing_event_type ADD VALUE IF NOT EXISTS '{loai}'")

    op.alter_column(
        "billing_events", "user_id", existing_type=sa.dialects.postgresql.UUID(), nullable=True
    )
    op.alter_column(
        "billing_events",
        "subscription_id",
        existing_type=sa.dialects.postgresql.UUID(),
        nullable=True,
    )


def downgrade() -> None:
    """Chi dao duoc phan NULLABLE, khong dao duoc phan enum.

    PostgreSQL khong co `ALTER TYPE ... DROP VALUE`. Cach duy nhat la dung mot type moi
    thieu bon gia tri nay roi chuyen moi cot phu thuoc sang — thao tac do THAT BAI giua
    chung neu da co du chi mot ban ghi mang gia tri moi, tuc dung vao luc downgrade de duoc
    goi nhat (rollback mot ban deploy da chay that). De nguyen gia tri enum thua thi vo
    hai: khong cot nao bat buoc phai dung toi no.

    Phan NULLABLE thi dao duoc, NHUNG chi khi chua co dong `unmatched_transfer` nao. Neu
    co thi lenh nay se do — do la dieu dung: xoa mat dau vet mot khoan tien that con te hon
    la downgrade that bai.
    """
    op.alter_column(
        "billing_events",
        "subscription_id",
        existing_type=sa.dialects.postgresql.UUID(),
        nullable=False,
    )
    op.alter_column(
        "billing_events", "user_id", existing_type=sa.dialects.postgresql.UUID(), nullable=False
    )
