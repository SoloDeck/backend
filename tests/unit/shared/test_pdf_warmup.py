"""Làm nóng WeasyPrint không bao giờ được làm hỏng việc khởi động."""

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

from src.shared.pdf_warmup import warm_up_pdf_engine


def _fake_weasyprint(html_cls: MagicMock) -> ModuleType:
    module = ModuleType("weasyprint")
    module.HTML = html_cls  # type: ignore[attr-defined]
    return module


def test_thanh_cong_thi_tra_so_giay_va_that_su_dung_pdf() -> None:
    html_cls = MagicMock()
    with patch.dict(sys.modules, {"weasyprint": _fake_weasyprint(html_cls)}):
        elapsed = warm_up_pdf_engine()

    assert elapsed is not None and elapsed >= 0
    html_cls.assert_called_once()
    html_cls.return_value.write_pdf.assert_called_once_with()


def test_thieu_thu_vien_he_thong_thi_tra_none_chu_khong_nem_loi() -> None:
    """Máy Windows chạy dev: `import weasyprint` ném OSError vì thiếu Pango/GTK."""
    broken = MagicMock(side_effect=OSError("cannot load library 'libgobject-2.0-0'"))

    class _Boom(ModuleType):
        def __getattr__(self, name: str) -> object:
            raise broken()

    with patch.dict(sys.modules, {"weasyprint": _Boom("weasyprint")}):
        assert warm_up_pdf_engine() is None


def test_dung_pdf_loi_giua_chung_cung_chi_ghi_canh_bao() -> None:
    html_cls = MagicMock()
    html_cls.return_value.write_pdf.side_effect = RuntimeError("font hỏng")
    with patch.dict(sys.modules, {"weasyprint": _fake_weasyprint(html_cls)}):
        assert warm_up_pdf_engine() is None
