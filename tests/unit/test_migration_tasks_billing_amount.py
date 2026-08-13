"""Phép chia tiền của migration `a4b5c6d7e8f9` (backfill `tasks.billing_amount`).

Vì sao đáng test riêng: migration này ĐỤNG DỮ LIỆU THẬT trên bản đã deploy, và phép chia
được CHÉP INLINE vào file migration (không `import src.`) nên nó không được che bởi test của
`milestone_money.py` nữa. Chép mà lệch một chỗ là ghi số tiền sai vào chứng từ tiền.

Nạp module theo đường dẫn: thư mục `alembic/versions` không phải package import được.
"""

import importlib.util
from decimal import Decimal
from pathlib import Path

_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "a4b5c6d7e8f9_tasks_billing_amount.py"
)
_spec = importlib.util.spec_from_file_location("_mig_billing_amount", _PATH)
assert _spec and _spec.loader
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)

_PRICE = Decimal(100_000_000)


class TestChiaTien:
    def test_theo_phan_tram(self) -> None:
        assert mig._split([("Cọc", 30), ("Bàn giao", 70)], _PRICE) == [
            Decimal(30_000_000),
            Decimal(70_000_000),
        ]

    def test_moc_khong_khai_phan_tram_thi_chia_deu_phan_con_lai(self) -> None:
        # Hợp đồng thật hay ghi "50% khi ký, phần còn lại khi bàn giao".
        assert mig._split([("Cọc", 50), ("Còn lại", None)], _PRICE) == [
            Decimal(50_000_000),
            Decimal(50_000_000),
        ]

    def test_tong_khop_tuyet_doi_du_lam_tron(self) -> None:
        # 33/33/34 chia 100 triệu. Đây chính là điều kiện mà backfill dùng để quyết định có
        # ghi hay không — lệch một đồng là cả deal bị bỏ qua.
        assert sum(mig._split([("A", 33), ("B", 33), ("C", 34)], _PRICE)) == _PRICE

    def test_hop_dong_ghi_130_phan_tram_thi_khong_tu_sua(self) -> None:
        # Không tự ép về 100%: bảng phải phản ánh thứ đã ký. Ở backfill thì deal kiểu này sẽ
        # rớt điều kiện "tổng khớp giá deal" và được để NULL — đúng như ý đồ.
        assert sum(mig._split([("A", 50), ("B", 50), ("C", 30)], _PRICE)) == Decimal(130_000_000)

    def test_chua_chot_gia_thi_khong_ra_tien(self) -> None:
        assert mig._split([("Cọc", 50)], Decimal(0)) == [Decimal(0)]

    def test_khong_co_moc_nao(self) -> None:
        assert mig._split([], _PRICE) == []


class TestDocMocTuContent:
    def test_shape_ai(self) -> None:
        assert mig._milestones_from_content(
            {"payment_milestones": [{"label": "Cọc", "percent": 50}]}
        ) == [("Cọc", 50)]

    def test_shape_dto_nam_trong_terms(self) -> None:
        assert mig._milestones_from_content(
            {"terms": {"payment_schedule": [{"description": "Đợt 1", "percentage": "40%"}]}}
        ) == [("Đợt 1", 40)]

    def test_content_la_chuoi_json(self) -> None:
        # Tuỳ driver, cột JSONB có thể về dạng chuỗi.
        assert mig._milestones_from_content('{"payment_milestones": [{"label": "A"}]}') == [
            ("A", None)
        ]

    def test_entry_hong_thi_bo_qua_chu_khong_no(self) -> None:
        assert mig._milestones_from_content(
            {"payment_milestones": ["Trả một lần", {"nolabel": 1}, 123]}
        ) == [("Trả một lần", None)]

    def test_content_rong_hay_hong(self) -> None:
        assert mig._milestones_from_content({}) == []
        assert mig._milestones_from_content(None) == []
        assert mig._milestones_from_content("không phải json") == []


class TestLichChuanTrungVoiBanChay:
    def test_default_khop_voi_default_payment_milestones(self) -> None:
        """Lịch 50/50 chép trong migration phải trùng bản trong `src`.

        Lệch nhau thì backfill tính ra một con số, còn runtime tính ra con số khác cho cùng
        một deal — mà đó đúng là loại lệch không ai phát hiện ra cho tới lúc đòi tiền.
        """
        from src.ai.proposal_generator.schemas.proposal_document import (
            default_payment_milestones,
        )

        expected = [(m.label, m.percent) for m in default_payment_milestones()]
        assert expected == mig._DEFAULT_MILESTONES

    def test_tien_to_khop_voi_bo_sinh_task(self) -> None:
        from src.modules.tasks.application.service import PAYMENT_TASK_PREFIX

        assert mig._LEGACY_PREFIX == PAYMENT_TASK_PREFIX
