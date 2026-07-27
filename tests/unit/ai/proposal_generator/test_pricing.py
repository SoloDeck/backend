"""Bộ định giá — luật tính tiền phải chứng minh được bằng test, không bằng lời hứa.

Đây là những test tôi sẽ chỉ vào nếu hội đồng hỏi "làm sao biết AI không tự bịa giá".  #Huynh
"""

from datetime import date
from decimal import Decimal

from src.ai.proposal_generator.pricing import (
    PriceAnchor,
    build_anchor,
    compute_quote,
    rush_factor_from_deadline,
    split_line_items,
)

M = Decimal(1_000_000)


class TestAnchor:
    """Mốc neo: dữ liệu THẬT trước, AI đoán sau cùng."""

    def test_dung_trung_vi_khong_dung_trung_binh(self) -> None:
        # 5 deal 30tr + 1 deal 500tr. Trung bình = 108tr (SAI BÉT). Trung vị = 30tr (ĐÚNG).
        # Nghề freelance đầy giá ngoại lai — đây chính là lý do phải dùng trung vị.
        values = [30 * M, 30 * M, 30 * M, 30 * M, 30 * M, 500 * M]
        anchor = build_anchor(
            same_category_values=values, any_category_values=[], market_low=None, market_high=None
        )
        assert anchor is not None
        assert anchor.value == 30 * M
        assert anchor.value != sum(values) / len(values)

    def test_du_3_deal_cung_nhom_thi_tin_cay_cao(self) -> None:
        anchor = build_anchor(
            same_category_values=[20 * M, 30 * M, 40 * M],
            any_category_values=[],
            market_low=None,
            market_high=None,
        )
        assert anchor is not None
        assert anchor.confidence == "high"
        assert anchor.sample_size == 3

    def test_it_hon_3_deal_thi_tin_cay_trung_binh(self) -> None:
        anchor = build_anchor(
            same_category_values=[20 * M, 40 * M],
            any_category_values=[],
            market_low=None,
            market_high=None,
        )
        assert anchor is not None
        assert anchor.confidence == "medium"

    def test_khong_co_cung_nhom_thi_noi_ra_moi_nhom(self) -> None:
        anchor = build_anchor(
            same_category_values=[],
            any_category_values=[50 * M, 60 * M, 70 * M],
            market_low=None,
            market_high=None,
        )
        assert anchor is not None
        assert anchor.value == 60 * M
        assert "mọi nhóm" in anchor.source

    def test_chua_chot_deal_nao_thi_roi_ve_gia_thi_truong_va_TU_NHAN_tin_cay_thap(self) -> None:
        anchor = build_anchor(
            same_category_values=[],
            any_category_values=[],
            market_low=30 * M,
            market_high=50 * M,
        )
        assert anchor is not None
        assert anchor.value == 40 * M  # điểm giữa khoảng
        assert anchor.confidence == "low"  # KHÔNG giấu dốt
        assert anchor.sample_size == 0

    def test_khong_neo_duoc_vao_dau_thi_tra_None_chu_khong_biadau_ra_mot_con_so(self) -> None:
        assert (
            build_anchor(
                same_category_values=[],
                any_category_values=[],
                market_low=None,
                market_high=None,
            )
            is None
        )


class TestRushFactor:
    """Độ gấp TÍNH BẰNG CODE — dòng duy nhất trong định giá không dính tới AI."""

    TODAY = date(2026, 7, 14)

    def test_khong_co_han_thi_khong_tinh_phu_phi(self) -> None:
        factor, reason = rush_factor_from_deadline(None, self.TODAY)
        assert factor == Decimal("1.0")
        assert "chưa nêu hạn" in reason

    def test_con_10_ngay_la_rat_gap(self) -> None:
        factor, reason = rush_factor_from_deadline(date(2026, 7, 24), self.TODAY)
        assert factor == Decimal("1.35")
        assert "10 ngày" in reason  # lý do phải nêu SỐ NGÀY để người dùng tự kiểm

    def test_con_25_ngay_la_kha_gap(self) -> None:
        factor, _ = rush_factor_from_deadline(date(2026, 8, 8), self.TODAY)
        assert factor == Decimal("1.15")

    def test_con_78_ngay_la_thoai_mai(self) -> None:
        factor, _ = rush_factor_from_deadline(date(2026, 9, 30), self.TODAY)
        assert factor == Decimal("1.0")

    def test_han_da_qua_thi_canh_bao(self) -> None:
        factor, reason = rush_factor_from_deadline(date(2026, 7, 1), self.TODAY)
        assert factor == Decimal("1.35")
        assert "ĐÃ QUA" in reason


class TestComputeQuote:
    TODAY = date(2026, 7, 14)

    def _anchor(self, value: Decimal = 38 * M, confidence: str = "high") -> PriceAnchor:
        return PriceAnchor(value=value, confidence=confidence, source="test", sample_size=3)  # type: ignore[arg-type]

    def test_nhan_ba_he_so_dung_thu_tu(self) -> None:
        # 38tr × 1.3 (phức tạp) × 1.2? -> scale "large" = 1.3 × 1.0 (không gấp) = 64,22tr
        # -> làm tròn 500k = 64,5tr
        quote = compute_quote(
            anchor=self._anchor(),
            complexity="complex",  # 1.3
            complexity_reason="5 phân hệ",
            scale="large",  # 1.3
            scale_reason="4 chi nhánh",
            deadline=date(2026, 9, 30),  # còn 78 ngày -> 1.0
            today=self.TODAY,
        )
        assert quote.complexity_factor == Decimal("1.3")
        assert quote.scale_factor == Decimal("1.3")
        assert quote.rush_factor == Decimal("1.0")
        # 38 × 1.3 × 1.3 = 64,22 -> tròn 500k
        assert quote.suggested == Decimal("64000000")

    def test_he_so_la_thi_roi_ve_binh_thuong_chu_khong_no(self) -> None:
        # Model trả về rác. Không được để nó lọt vào phép nhân tiền thật.
        quote = compute_quote(
            anchor=self._anchor(),
            complexity="cực kỳ khoai",
            complexity_reason="",
            scale="?????",
            scale_reason="",
            deadline=None,
            today=self.TODAY,
        )
        assert quote.complexity_factor == Decimal("1.0")
        assert quote.scale_factor == Decimal("1.0")
        assert quote.suggested == 38 * M

    def test_do_tin_cay_CAO_thi_khoang_HEP(self) -> None:
        quote = compute_quote(
            anchor=self._anchor(confidence="high"),
            complexity="normal",
            complexity_reason="",
            scale="normal",
            scale_reason="",
            deadline=None,
            today=self.TODAY,
        )
        # ±10%
        assert quote.range_min == Decimal("34000000")
        assert quote.range_max == Decimal("42000000")

    def test_do_tin_cay_THAP_thi_khoang_RONG_TOAC(self) -> None:
        # Khoảng rộng là LỜI THÚ NHẬN rằng hệ thống không dám chắc.
        quote = compute_quote(
            anchor=self._anchor(confidence="low"),
            complexity="normal",
            complexity_reason="",
            scale="normal",
            scale_reason="",
            deadline=None,
            today=self.TODAY,
        )
        # ±30%
        assert quote.range_min == Decimal("26500000")
        assert quote.range_max == Decimal("49500000")
        assert quote.range_max - quote.range_min > 20 * M

    def test_gia_cao_hon_ngan_sach_khach_thi_CANH_BAO_chu_khong_TU_HA_GIA(self) -> None:
        quote = compute_quote(
            anchor=self._anchor(value=80 * M),
            complexity="normal",
            complexity_reason="",
            scale="normal",
            scale_reason="",
            deadline=None,
            client_budget=30 * M,
            today=self.TODAY,
        )
        assert quote.suggested == 80 * M  # KHÔNG tự hạ xuống cho vừa túi khách
        assert any("nguy cơ mất deal" in w for w in quote.warnings)

    def test_khach_co_ngan_sach_cao_hon_thi_bao_con_du_dia(self) -> None:
        quote = compute_quote(
            anchor=self._anchor(value=40 * M),
            complexity="normal",
            complexity_reason="",
            scale="normal",
            scale_reason="",
            deadline=None,
            client_budget=120 * M,
            today=self.TODAY,
        )
        assert any("dư địa nâng giá" in w for w in quote.warnings)


class TestLineItems:
    def test_tong_cac_dong_KHOP_TUYET_DOI_voi_tong_bao_gia(self) -> None:
        # Bảng cộng không ra tổng là thứ khách soi ra ngay. Phần lẻ do làm tròn phải được
        # dồn vào dòng cuối.
        total = Decimal("59000000")
        items = split_line_items(
            total,
            [
                {"label": "Quản lý bàn & gọi món QR", "weight": 30},
                {"label": "Quản lý kho", "weight": 25},
                {"label": "Báo cáo doanh thu", "weight": 20},
                {"label": "In bill máy nhiệt", "weight": 15},
                {"label": "Thiết kế giao diện", "weight": 10},
            ],
        )
        assert len(items) == 5
        assert sum(item["amount"] for item in items) == int(total)

    def test_ti_trong_khong_cong_ra_100_van_duoc_chuan_hoa(self) -> None:
        # Model trả 3/4/5 (tổng 12) chứ không phải phần trăm. Vẫn phải chia đúng.
        items = split_line_items(
            Decimal("12000000"),
            [
                {"label": "A", "weight": 3},
                {"label": "B", "weight": 4},
                {"label": "C", "weight": 5},
            ],
        )
        assert sum(item["amount"] for item in items) == 12_000_000
        assert sum(item["weight_percent"] for item in items) == 100

    def test_khong_co_hang_muc_thi_tra_mang_rong(self) -> None:
        assert split_line_items(Decimal("10000000"), None) == []
        assert split_line_items(Decimal("10000000"), []) == []

    def test_bo_hang_muc_khong_ten_hoac_ti_trong_0(self) -> None:
        items = split_line_items(
            Decimal("10000000"),
            [
                {"label": "Thật", "weight": 10},
                {"label": "", "weight": 5},
                {"label": "Tỉ trọng 0", "weight": 0},
            ],
        )
        assert len(items) == 1
        assert items[0]["label"] == "Thật"
