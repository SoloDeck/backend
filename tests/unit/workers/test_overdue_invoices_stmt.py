"""Câu truy vấn của job đánh dấu hoá đơn quá hạn.

Job vẫn đánh dấu quá hạn cho mọi hoá đơn, nhưng cần biết deal/khách đã bị xoá chưa để KHÔNG
reo chuông cho dữ liệu đã xoá — bấm vào thông báo đó chỉ ra trang "Không tìm thấy dự án".
"""

from datetime import date

from sqlalchemy.dialects import postgresql

from src.workers.reminder_jobs.tasks import overdue_invoices_stmt


def _sql() -> str:
    return str(
        overdue_invoices_stmt(date(2026, 9, 13)).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def test_noi_ngoai_voi_deal_de_hoa_don_chi_gan_hop_dong_van_duoc_xet() -> None:
    assert "LEFT OUTER JOIN deals" in _sql()


def test_lay_kem_moc_xoa_cua_deal_va_khach() -> None:
    sql = _sql()
    assert "deals.deleted_at AS deal_deleted_at" in sql
    assert "clients.deleted_at AS client_deleted_at" in sql


def test_chi_hoa_don_da_gui_va_qua_han() -> None:
    sql = _sql()
    assert "invoices.due_date < '2026-09-13'" in sql
    assert "'sent', 'partially_paid'" in sql
