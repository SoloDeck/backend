"""merge configurable-LLM-model branch with main after #92 and #101 landed

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8, f8a9b0c1d2e3
Create Date: 2026-08-19 00:00:00.000000

#92 va #101 da vao main, keo theo mocs hop nhat f8a9b0c1d2e3 cua #92. Nhanh nay
dang o c3d4e5f6a7b8 (hop nhat #96 voi nhanh model). Hai head.

KHONG doi cha cua bat ky ban nao trong hai: ca hai deu da day len remote. Doi cha
cua mot revision DA PHAT HANH khien may nao tung `upgrade head` coi nhu dang o head
roi va LANG LE bo qua moi ban nam giua; CI khong bat duoc vi CI luon dung tu DB rong.

Ca hai nhanh khong dung cot nao chung nen nut hop nhat de rong.
"""

from collections.abc import Sequence

revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = ("c3d4e5f6a7b8", "f8a9b0c1d2e3")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
