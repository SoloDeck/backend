"""ContractClauses ép kiểu được đầu ra lởm của model, và parties dựng từ DB."""

from src.ai.contract_generator.schemas.contract_content import (
    ContractClauses,
    build_parties,
)


class TestContractClauses:
    def test_giu_nguyen_chuoi_binh_thuong(self) -> None:
        clauses = ContractClauses.model_validate(
            {
                "scope_of_work": "Thiết kế logo.",
                "payment_terms": "Thanh toán 100% trước.",
                "revision_policy": "2 lần sửa miễn phí.",
                "ip_ownership": "Chuyển giao sau khi thanh toán đủ.",
                "termination_clause": "Báo trước 7 ngày.",
                "custom_clauses": "",
            }
        )

        assert clauses.scope_of_work == "Thiết kế logo."
        assert clauses.custom_clauses == ""

    def test_ep_mang_thanh_chuoi(self) -> None:
        """llama-4-scout hay trả mảng gạch đầu dòng dù prompt yêu cầu chuỗi."""
        clauses = ContractClauses.model_validate(
            {
                "scope_of_work": ["Thiết kế logo", "Bàn giao file AI"],
                "payment_terms": "Thanh toán 100% trước.",
                "revision_policy": "2 lần sửa.",
                "ip_ownership": "Chuyển giao.",
                "termination_clause": "Báo trước 7 ngày.",
            }
        )

        assert clauses.scope_of_work == "Thiết kế logo\nBàn giao file AI"

    def test_ep_object_thanh_chuoi(self) -> None:
        clauses = ContractClauses.model_validate(
            {
                "scope_of_work": "Thiết kế logo.",
                "payment_terms": {"tong": "700.000 d", "tien_do": "100% truoc"},
                "revision_policy": "2 lần sửa.",
                "ip_ownership": "Chuyển giao.",
                "termination_clause": "Báo trước 7 ngày.",
            }
        )

        assert "tong: 700.000 d" in clauses.payment_terms
        assert "tien_do: 100% truoc" in clauses.payment_terms

    def test_custom_clauses_thieu_thi_rong(self) -> None:
        clauses = ContractClauses.model_validate(
            {
                "scope_of_work": "Thiết kế logo.",
                "payment_terms": "Thanh toán 100% trước.",
                "revision_policy": "2 lần sửa.",
                "ip_ownership": "Chuyển giao.",
                "termination_clause": "Báo trước 7 ngày.",
            }
        )

        assert clauses.custom_clauses == ""

    def test_khong_co_truong_parties(self) -> None:
        """parties KHÔNG được nằm trong schema AI — model không được phép viết."""
        assert "parties" not in ContractClauses.model_fields
        assert "governing_law" not in ContractClauses.model_fields


class TestBuildParties:
    def test_lay_tu_du_lieu_db(self) -> None:
        parties = build_parties(
            client_data={"name": "Nguyễn Văn Mười", "email": "ngvan10@gmail.com"},
            user_profile={
                "name": "Huỳnh Hoa",
                "email": "hoa@example.com",
                "business_name": "Hộ kinh doanh Hoa Design",
            },
        )

        assert parties["client"]["name"] == "Nguyễn Văn Mười"
        assert parties["client"]["email"] == "ngvan10@gmail.com"
        assert parties["freelancer"]["name"] == "Huỳnh Hoa"
        assert parties["freelancer"]["business_name"] == "Hộ kinh doanh Hoa Design"

    def test_thieu_du_lieu_thi_de_rong_chu_khong_bia(self) -> None:
        parties = build_parties(client_data={}, user_profile={})

        assert parties["client"]["name"] == ""
        assert parties["client"]["address"] == ""
        assert parties["freelancer"]["business_name"] == ""
