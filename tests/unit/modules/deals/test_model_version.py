"""Lịch sử chấm điểm phải ghi đúng MODEL THẬT đã chạy, không phải chuỗi cứng."""

from types import SimpleNamespace

import pytest

from src.ai.facade import AIFacade
from src.modules.deals.application.service import _resolve_model_version


class TestResolveModelVersion:
    def test_uu_tien_model_used_trong_usage_cung_nguon_voi_bang_chi_phi_ai(self) -> None:
        usage = {"model_used": "gemini-2.5-flash", "input_tokens": 1}
        assert _resolve_model_version("ten-khac", usage) == "gemini-2.5-flash"

    def test_provider_khong_bao_usage_thi_dung_ten_model_cua_provider(self) -> None:
        assert _resolve_model_version("gemini-2.5-flash", None) == "gemini-2.5-flash"

    def test_usage_thieu_ten_thi_roi_ve_ten_cua_provider(self) -> None:
        assert _resolve_model_version("llama-3.3-70b", {"model_used": "  "}) == "llama-3.3-70b"

    def test_khong_biet_thi_ghi_unknown_chu_khong_bia_ra_ten_model(self) -> None:
        assert _resolve_model_version(None, None) == "unknown"
        assert "llama" not in _resolve_model_version(None, {})

    def test_cat_theo_do_dai_cot(self) -> None:
        assert len(_resolve_model_version("m" * 300, None)) == 100


class TestFacadeLastModel:
    @staticmethod
    def _facade(**modules: object) -> AIFacade:
        facade = AIFacade.__new__(AIFacade)  # bỏ qua __init__: chỉ cần các module giả
        for name, value in modules.items():
            setattr(facade, name, value)
        return facade

    def test_doc_model_cua_lan_goi_gan_nhat(self) -> None:
        facade = self._facade(lead_qualifier=SimpleNamespace(last_model="gemini-2.5-flash"))
        assert facade.last_model("lead_qualifier") == "gemini-2.5-flash"

    @pytest.mark.parametrize("value", [None, "", 123])
    def test_chua_goi_hoac_khong_phai_chuoi_thi_none(self, value: object) -> None:
        facade = self._facade(lead_qualifier=SimpleNamespace(last_model=value))
        assert facade.last_model("lead_qualifier") is None

    def test_module_khong_ton_tai_thi_none(self) -> None:
        assert self._facade().last_model("khong_co") is None
