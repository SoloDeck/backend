"""Backend cộng điểm, không tin số tổng của LLM; nhãn suy ra từ điểm."""

from src.ai.lead_qualifier.scoring import (
    READINESS_CRITERIA,
    compute_readiness,
    compute_win_likelihood,
    level_from_score,
)

FULL_MARKS = {
    "scope": {"points": 30, "reason": "Rõ ràng"},
    "budget": {"points": 25, "reason": "Có con số"},
    "timeline": {"points": 20, "reason": "Có mốc"},
    "detail": {"points": 15, "reason": "Rất chi tiết"},
    "context": {"points": 10, "reason": "Đủ bối cảnh"},
}


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
