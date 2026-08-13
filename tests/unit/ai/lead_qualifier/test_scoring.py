"""Backend cộng điểm, không tin số tổng của LLM; nhãn suy ra từ điểm."""

from typing import Any

from src.ai.lead_qualifier.scoring import (
    DEFAULT_ASK,
    ESSENTIAL_CRITERIA,
    FILL_FIELD,
    HOT_THRESHOLD,
    READINESS_CRITERIA,
    RUBRIC_LEVELS,
    build_gap_summary,
    compute_readiness,
    compute_win_likelihood,
    explain_gap,
    level_from_score,
    normalize_price_range,
    snap_to_level,
)

FULL_MARKS = {
    "scope": {"points": 30, "reason": "Rõ ràng"},
    "budget": {"points": 25, "reason": "Có con số"},
    "timeline": {"points": 20, "reason": "Có mốc"},
    "detail": {"points": 15, "reason": "Rất chi tiết"},
    "context": {"points": 10, "reason": "Đủ bối cảnh"},
}

# Deal 27/100 — đúng ví dụ mentor đưa ra: chỉ có tên dự án, khách chưa nói tiền, thời gian
# nói mơ hồ, không mô tả gì thêm, biết lõm bõm bối cảnh.
DEAL_27 = {"scope": 12, "budget": 0, "timeline": 10, "detail": 0, "context": 5}


class TestComputeReadiness:
    def test_cong_du_100(self) -> None:
        score, breakdown = compute_readiness(FULL_MARKS)

        assert score == 100
        assert len(breakdown) == len(READINESS_CRITERIA)

    def test_kep_diem_vuot_tran_cua_tieu_chi(self) -> None:
        """Model chấm scope 999 cũng chỉ được tối đa 30 — không cho nó tự phá thang."""
        score, breakdown = compute_readiness({**FULL_MARKS, "scope": {"points": 999}})

        assert score == 100
        scope = next(item for item in breakdown if item["key"] == "scope")
        assert scope["points"] == 30

    def test_thieu_tieu_chi_thi_tinh_0_chu_khong_no(self) -> None:
        score, breakdown = compute_readiness({"budget": {"points": 25}})

        assert score == 25
        assert len(breakdown) == len(READINESS_CRITERIA)

    def test_chiu_duoc_khi_model_tra_so_tran(self) -> None:
        """Prompt bảo trả {"points":..,"reason":..} nhưng model hay trả thẳng số."""
        score, _ = compute_readiness({"scope": 30, "budget": 25})

        assert score == 55

    def test_model_tra_rac_thi_ve_0_chu_khong_no(self) -> None:
        assert compute_readiness(None)[0] == 0
        assert compute_readiness("mot dong text")[0] == 0
        assert compute_readiness({"scope": "ba muoi"})[0] == 0

    def test_giu_lai_ly_do_de_nguoi_dung_kiem_chung(self) -> None:
        _, breakdown = compute_readiness(FULL_MARKS)

        budget = next(item for item in breakdown if item["key"] == "budget")
        assert budget["reason"] == "Có con số"
        assert budget["max_points"] == 25

    def test_diem_lech_nac_bi_keo_ve_nac_hop_le(self) -> None:
        """Model chấm 22 thì bảng bên cạnh ghi "đang ở nấc 20" — hai chỗ không được đá nhau."""
        score, breakdown = compute_readiness({"scope": 22})

        scope = next(item for item in breakdown if item["key"] == "scope")
        assert scope["points"] == 20
        assert score == 20

    def test_dat_tran_thi_khong_hoi_gi_them(self) -> None:
        _, breakdown = compute_readiness(FULL_MARKS)

        for item in breakdown:
            assert item["gap"] is None, item["key"]
            assert item["ask"] is None, item["key"]

    def test_thieu_diem_thi_luon_kem_phan_giai_thich_va_cau_hoi(self) -> None:
        _, breakdown = compute_readiness(DEAL_27)

        for item in breakdown:
            assert item["gap"], item["key"]
            assert item["ask"], item["key"]

    def test_ai_khong_tra_cau_hoi_thi_roi_ve_cau_mau(self) -> None:
        _, breakdown = compute_readiness({"budget": {"points": 0, "reason": "Chưa nhắc tới tiền"}})

        budget = next(item for item in breakdown if item["key"] == "budget")
        assert budget["ask"] == DEFAULT_ASK["budget"]

    def test_giu_cau_hoi_ai_viet_vi_no_bam_dung_du_an(self) -> None:
        _, breakdown = compute_readiness(
            {"budget": {"points": 0, "question": "Shop mình dự trù bao nhiêu cho web bán vợt ạ?"}}
        )

        budget = next(item for item in breakdown if item["key"] == "budget")
        assert budget["ask"] == "Shop mình dự trù bao nhiêu cho web bán vợt ạ?"


class TestRubricLevels:
    """Barem là thứ trả lời "vì sao MẤT điểm" — nó lệch thì cả phần giải thích lệch theo."""

    def test_nac_cao_nhat_dung_bang_tran_cua_tieu_chi(self) -> None:
        for key, levels in RUBRIC_LEVELS.items():
            assert levels[0].points == READINESS_CRITERIA[key]

    def test_nac_khai_giam_dan_khong_trung_va_ket_thuc_o_0(self) -> None:
        for key, levels in RUBRIC_LEVELS.items():
            points = [level.points for level in levels]
            assert points == sorted(points, reverse=True), key
            assert points[-1] == 0, key
            assert len(set(points)) == len(points), key

    def test_moi_nac_deu_noi_duoc_dang_o_dau_va_can_gi_de_dat(self) -> None:
        for levels in RUBRIC_LEVELS.values():
            for level in levels:
                assert level.state.strip()
                assert level.requirement.strip()

    def test_du_ca_5_tieu_chi_khong_thieu_cai_nao(self) -> None:
        assert set(RUBRIC_LEVELS) == set(READINESS_CRITERIA)

    def test_ba_tieu_chi_thiet_yeu_cong_dung_bang_nguong_hot(self) -> None:
        """HOT = 75 = scope + budget + timeline.

        Đây là ĐỊNH NGHĨA của HOT ("đủ ba thứ cốt lõi để báo giá tự tin"), không phải một
        con số tròn chọn cho đẹp. Đổi trọng số mà quên ngưỡng là mất luôn lập luận đó.
        """
        assert sum(READINESS_CRITERIA[key] for key in ESSENTIAL_CRITERIA) == HOT_THRESHOLD

    def test_tong_trong_so_van_la_100(self) -> None:
        assert sum(READINESS_CRITERIA.values()) == 100

    def test_moi_tieu_chi_deu_co_cau_hoi_mau_va_o_de_dien(self) -> None:
        """Không có câu mẫu thì AI im lặng một phát là màn hình trống đúng chỗ cần đọc."""
        for key in READINESS_CRITERIA:
            assert DEFAULT_ASK[key].strip().endswith("?"), key
            assert FILL_FIELD[key].strip(), key


class TestSnapToLevel:
    def test_diem_nam_giua_hai_nac_thi_keo_xuong(self) -> None:
        """Prompt cấm chấm 22, nhưng prompt là lời khuyên — backend mới là ràng buộc."""
        assert snap_to_level("scope", 22) == 20
        assert snap_to_level("budget", 24) == 15
        assert snap_to_level("timeline", 19) == 10
        assert snap_to_level("detail", 14) == 8
        assert snap_to_level("context", 9) == 5

    def test_diem_dung_nac_thi_giu_nguyen(self) -> None:
        for key, levels in RUBRIC_LEVELS.items():
            for level in levels:
                assert snap_to_level(key, level.points) == level.points

    def test_tieu_chi_ngoai_barem_thi_khong_dong_vao(self) -> None:
        """`source` thuộc thang khả năng chốt, không có barem — đừng kéo nhầm."""
        assert snap_to_level("source", 17) == 17


class TestExplainGap:
    def test_dat_tran_thi_khong_con_gi_de_giai_thich(self) -> None:
        for key, levels in RUBRIC_LEVELS.items():
            assert explain_gap(key, levels[0].points) is None

    def test_noi_duoc_mat_bao_nhieu_dang_o_dau_va_len_tung_nac_can_gi(self) -> None:
        gap = explain_gap("scope", 12)

        assert gap is not None
        assert gap["lost_points"] == 18
        assert "tên dự án" in gap["current_state"]
        assert [step["points"] for step in gap["steps"]] == [20, 30]
        assert [step["gain"] for step in gap["steps"]] == [8, 18]
        assert all(step["requirement"].strip() for step in gap["steps"])

    def test_0_diem_thi_thay_ca_bac_thang_chu_khong_chi_dinh(self) -> None:
        """Khách nói mơ hồ về tiền vẫn hơn không nói gì — nấc giữa phải nhìn thấy."""
        gap = explain_gap("budget", 0)

        assert gap is not None
        assert [step["points"] for step in gap["steps"]] == [15, 25]

    def test_chi_ra_o_nao_dien_vao_de_bu_diem(self) -> None:
        """Biết thiếu gì mà không biết điền vào đâu thì luồng vẫn đứt."""
        budget = explain_gap("budget", 0)
        timeline = explain_gap("timeline", 0)

        assert budget is not None and budget["fill_field"] == "client_budget"
        assert timeline is not None and timeline["fill_field"] == "desired_timeline"


class TestBuildGapSummary:
    def test_tong_diem_mat_dung_bang_phan_con_thieu(self) -> None:
        score, breakdown = compute_readiness(DEAL_27)
        summary = build_gap_summary(score, breakdown)

        assert score == 27
        assert summary["lost_points"] == 73
        assert sum(gap["lost_points"] for gap in summary["gaps"]) == 73

    def test_sap_theo_diem_mat_nhieu_nhat_truoc(self) -> None:
        """Hỏi một câu về ngân sách được 25 điểm, làm rõ bối cảnh chỉ được 10.

        Thứ tự đó phải nhìn thấy ngay, đừng bắt người dùng tự so.
        """
        score, breakdown = compute_readiness(DEAL_27)
        summary = build_gap_summary(score, breakdown)

        assert [gap["key"] for gap in summary["gaps"]] == [
            "budget",
            "scope",
            "detail",
            "timeline",
            "context",
        ]

    def test_diem_tuyet_doi_thi_khong_con_gi_de_hoi(self) -> None:
        score, breakdown = compute_readiness(FULL_MARKS)
        summary = build_gap_summary(score, breakdown)

        assert summary["gaps"] == []
        assert summary["essential_missing"] == []
        assert summary["lost_points"] == 0
        assert summary["points_to_hot"] == 0

    def test_chi_ra_tieu_chi_thiet_yeu_dang_thieu(self) -> None:
        score, breakdown = compute_readiness(
            {"scope": 30, "budget": 0, "timeline": 0, "detail": 15, "context": 10}
        )
        summary = build_gap_summary(score, breakdown)

        assert score == 55
        assert summary["essential_missing"] == ["budget", "timeline"]
        assert summary["points_to_hot"] == 20

    def test_ban_ghi_cu_khong_co_gap_van_tinh_lai_duoc(self) -> None:
        """Bản đánh giá lưu TRƯỚC khi có tính năng này chỉ có điểm và lý do.

        Không tính lại thì mở bản cũ ra sẽ trống đúng chỗ quan trọng nhất — mà gap suy ra
        thuần tuý từ (tiêu chí, điểm) nên tính lại được.
        """
        legacy: list[dict[str, Any]] = [
            {"key": "scope", "label": "Phạm vi công việc", "points": 30, "max_points": 30},
            {"key": "budget", "label": "Ngân sách", "points": 0, "max_points": 25},
        ]
        summary = build_gap_summary(30, legacy)

        assert [gap["key"] for gap in summary["gaps"]] == ["budget"]
        assert summary["gaps"][0]["lost_points"] == 25
        assert summary["gaps"][0]["ask"] == DEFAULT_ASK["budget"]
        assert summary["gaps"][0]["steps"][0]["points"] == 15

    def test_bo_qua_tieu_chi_la_thay_vi_no(self) -> None:
        """`source` của thang khả năng chốt lọt vào thì bỏ, đừng cho nổ index."""
        summary = build_gap_summary(
            0, [{"key": "source", "label": "Nguồn deal", "points": 10, "max_points": 25}]
        )

        assert summary["gaps"] == []


class TestLevelFromScore:
    def test_nguong_khop_voi_frontend(self) -> None:
        assert level_from_score(75) == "HOT"
        assert level_from_score(74) == "WARM"
        assert level_from_score(45) == "WARM"
        assert level_from_score(44) == "COLD"


class TestComputeWinLikelihood:
    def test_du_tin_hieu_tot_thi_kha_nang_chot_cao(self) -> None:
        win = compute_win_likelihood(
            budget_points=25,
            timeline_points=20,
            detail_points=12,
            estimated_value=35_000_000,
            price_range_min=30_000_000,
            source="referral",
        )

        assert win["level"] == "high"
        assert win["score"] >= 70

    def test_khach_khong_neu_thoi_han_thi_khong_duoc_full_diem(self) -> None:
        """Chính con bug người dùng bắt được.

        Bản đầu tôi dò chuỗi: `"không đủ thông tin" not in timeline_signal`. AI trả
        "Không có thông tin về thời gian thực hiện dự án" — không chứa đúng cụm đó, nên
        thành True và thời gian được 25/25, trong khi bảng bên cạnh ghi 0/20. Giờ điểm
        lấy thẳng từ bảng phân rã nên hai bảng không thể mâu thuẫn.
        """
        win = compute_win_likelihood(
            budget_points=0,
            timeline_points=0,  # bảng phân rã nói: khách không nêu thời hạn
            detail_points=0,
            estimated_value=200_000,
            price_range_min=5_000_000,
            source="inbound",
        )

        timeline = next(f for f in win["factors"] if f["label"] == "Thời gian")
        assert timeline["points"] == 0
        assert timeline["impact"] == "negative"

    def test_gia_tri_du_kien_cua_freelancer_khong_phai_ngan_sach_khach(self) -> None:
        """Bug thứ hai người dùng bắt được.

        Ô "Giá trị dự kiến" trong form là do FREELANCER tự ước. Trước đây nó bị đưa vào
        AI dưới nhãn "Estimated value" và AI tưởng khách đã báo ngân sách → chấm 20/25.
        Giờ khi khách không nêu tiền (budget_points = 0), yếu tố ngân sách phải là 0 và
        TRUNG LẬP — thiếu thông tin, chứ không phải tín hiệu xấu.
        """
        win = compute_win_likelihood(
            budget_points=0,  # khách KHÔNG nêu ngân sách
            timeline_points=15,
            detail_points=10,
            estimated_value=200_000,  # freelancer tự nhập — không được dùng làm bằng chứng
            price_range_min=10_000_000,
            source="referral",
        )

        budget = next(f for f in win["factors"] if f["label"] == "Ngân sách")
        assert budget["points"] == 0
        assert budget["impact"] == "neutral"
        assert "chưa nêu ngân sách" in budget["reason"]

    def test_khach_neu_ngan_sach_thap_hon_nhieu_thi_la_canh_bao(self) -> None:
        win = compute_win_likelihood(
            budget_points=22,  # khách CÓ nêu ngân sách
            timeline_points=0,
            detail_points=2,
            estimated_value=500_000,
            price_range_min=5_000_000,
            source="outreach",
        )

        assert win["level"] == "low"
        budget = next(f for f in win["factors"] if f["label"] == "Ngân sách")
        assert budget["impact"] == "negative"
        assert budget["points"] == 0

    def test_moi_yeu_to_deu_phai_neu_ly_do(self) -> None:
        """Không có lý do thì người dùng không kiểm chứng được — cả điểm số mất giá trị."""
        win = compute_win_likelihood(
            budget_points=20,
            timeline_points=18,
            detail_points=10,
            estimated_value=10_000_000,
            price_range_min=10_000_000,
            source="inbound",
        )

        assert len(win["factors"]) == 4
        for factor in win["factors"]:
            assert factor["reason"].strip()
            assert factor["impact"] in {"positive", "neutral", "negative"}


class TestNormalizePriceRange:
    """Model viết tắt "30 triệu" thành 30 → giao diện in ra "30 ₫". Chặn ở backend."""

    def test_viet_tat_theo_trieu_thi_nhan_len(self) -> None:
        assert normalize_price_range(30, 50) == (30_000_000, 50_000_000)

    def test_so_day_du_thi_giu_nguyen(self) -> None:
        assert normalize_price_range(30_000_000, 45_000_000) == (30_000_000, 45_000_000)

    def test_so_lung_chung_thi_tra_0_chu_khong_doan(self) -> None:
        """1.000–500.000: không đoán nổi ý model. Thà không hiện gì còn hơn hiện sai."""
        assert normalize_price_range(50_000, 90_000) == (0, 0)

    def test_khong_uoc_luong_duoc_thi_van_la_0(self) -> None:
        assert normalize_price_range(0, 0) == (0, 0)
        assert normalize_price_range(None, None) == (0, 0)

    def test_model_tra_rac_thi_ve_0_chu_khong_no(self) -> None:
        assert normalize_price_range("ba muoi trieu", []) == (0, 0)
