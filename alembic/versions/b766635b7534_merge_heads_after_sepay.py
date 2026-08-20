"""merge the two heads left on main by #117

Revision ID: b766635b7534
Revises: e6f7a8b9c0d1, f6a7b8c9d0e1
Create Date: 2026-08-20 00:00:00.000000

main dang co HAI head, nen moi PR lai chet o buoc dung DB voi
"Multiple head revisions are present for given argument 'head'" — dung con loi ma #116
vua sua xong.

  e6f7a8b9c0d1  #116 — noi a1b2c3d4e5f6 (enum zalopay) voi d4e5f6a7b8c9 (llm-model)
  f6a7b8c9d0e1  #117 — noi d4e5f6a7b8c9 voi chuoi SePay (… -> e5f6a7b8c9d0)

Hai ban duoc viet doc lap trong cung mot gio, deu tieu thu d4e5f6a7b8c9, nen gop lai
thanh dung hai tip. #117 co mot commit thay f6a7b8c9d0e1 bang mot nut noi thang vao
e6f7a8b9c0d1, nhung commit do khong nam trong lan merge — #117 duoc merge tu trang thai
truoc do.

O day KHONG xoa f6a7b8c9d0e1 nua: no da len main, tuc la da phat hanh. Chi them mot nut
moi noi hai head lai. Do cung la cach #116 da lam, va la cach an toan cho moi DB da tung
`upgrade head`.

Vi sao CI khong bat: hai file merge co ten khac nhau nen git khong thay xung dot van ban.
Xung dot o day la ve NGU NGHIA, chi alembic nhin ra, va chi khi chay `upgrade head`.

Id lay ngau nhien, khong noi tiep day doan duoc.

Khong co DDL: chi noi lai cay revision.
"""

from collections.abc import Sequence

revision: str = "b766635b7534"
down_revision: str | Sequence[str] | None = ("e6f7a8b9c0d1", "f6a7b8c9d0e1")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
