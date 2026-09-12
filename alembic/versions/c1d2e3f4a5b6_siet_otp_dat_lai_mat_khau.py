"""siet OTP dat lai mat khau: bo UNIQUE token_hash, them cot attempts

Revision ID: c1d2e3f4a5b6
Revises: b766635b7534
Create Date: 2026-09-12 00:00:00.000000

Hai thay doi, deu phuc vu mot lo hong: doan duoc OTP la chiem duoc tai khoan.

1. BO `uq_password_reset_tokens_hash`.
   Ma OTP chi co 6 chu so, tuc dung 1.000.000 gia tri hash co the co, va bang nay khong
   bao gio duoc don. Hai nguoi dung khac nhau xin ma cung luc ma trung so la lan INSERT
   thu hai vo rang buoc UNIQUE -> 500, nguoi do khong dat lai duoc mat khau. Rang buoc nay
   cung khong bao ve gi: ke tu ban sua nay, ma con duoc tra theo CA user_id, nen hai nguoi
   trung ma khong con lam lo du lieu cua nhau.

2. THEM cot `attempts` (mac dinh 0).
   Truoc day khong co cho nao dem so lan go sai, nen ke tan cong ban thu tu 000000 len
   khong gioi han. Nay moi lan go sai cong mot, qua nguong thi ma bi huy, phai xin ma moi.

Khong dung tu dong sinh: viet tay de kem duoc phan giai thich. Co ban `downgrade` that
de lui duoc, nhung luu y lui se dung lai UNIQUE va do la lui ve trang thai co loi 500.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | Sequence[str] | None = "b766635b7534"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # IF EXISTS: co DB dung tu truoc lan sua ten rang buoc, khong nen chet vi chuyen do.
    op.execute(
        "ALTER TABLE password_reset_tokens "
        "DROP CONSTRAINT IF EXISTS uq_password_reset_tokens_hash"
    )
    # Tra ma van phai nhanh, chi la khong con doi duy nhat.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_hash "
        "ON password_reset_tokens (token_hash)"
    )
    op.add_column(
        "password_reset_tokens",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("password_reset_tokens", "attempts")
    op.execute("DROP INDEX IF EXISTS idx_password_reset_tokens_hash")
    op.execute(
        "ALTER TABLE password_reset_tokens "
        "ADD CONSTRAINT uq_password_reset_tokens_hash UNIQUE (token_hash)"
    )
