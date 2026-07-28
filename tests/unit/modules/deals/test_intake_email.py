"""Email báo freelancer có Deal mới từ form intake.

Thư này quyết định freelancer có kịp chăm khách hay không, nên kiểm: có tên khách, có
link đúng deal, và không vỡ khi tên dự án/tên chủ để trống.
"""

from src.modules.deals.application.emails import build_new_deal_email


class TestBuildNewDealEmail:
    def test_co_ten_khach_va_link_deal(self) -> None:
        content = build_new_deal_email(
            owner_name="Nguyễn Văn A",
            client_name="Quán cà phê Nắng",
            project_name="Website bán hàng",
            deal_url="https://app.solodesk.space/deals/abc-123",
        )
        assert "Quán cà phê Nắng" in content.plain
        assert "Website bán hàng" in content.plain
        assert "https://app.solodesk.space/deals/abc-123" in content.plain
        assert "https://app.solodesk.space/deals/abc-123" in content.html
        # Tiêu đề mang luôn TÊN DỰ ÁN: freelancer lướt hộp thư thấy ngay việc gì, không
        # phải mở từng thư ra mới biết khách hỏi cái gì.
        assert content.subject == "[SoloDesk] Deal mới: Website bán hàng — Quán cà phê Nắng"

    def test_thieu_ten_du_an_va_ten_chu_van_on(self) -> None:
        content = build_new_deal_email(
            owner_name=None,
            client_name="Khách lẻ",
            project_name=None,
            deal_url="https://app.solodesk.space/deals/x",
        )
        assert "bạn" in content.plain  # fallback lời chào
        assert "một dự án mới" in content.plain  # fallback tên dự án

    def test_html_escape_chong_chen_the(self) -> None:
        content = build_new_deal_email(
            owner_name="A",
            client_name="<script>alert(1)</script>",
            project_name="Dự án <b>X</b>",
            deal_url="https://app.solodesk.space/deals/x",
            # Trường nào cũng do người lạ trên internet gõ vào form công khai.
            client_email="<img src=x onerror=alert(1)>",
            inquiry_text="<script>xss()</script>",
        )
        # Escape làm mã trở thành CHỮ vô hại: chuỗi "onerror=" vẫn còn nhưng không còn nằm
        # trong một thẻ nào, nên trình đọc mail không chạy nó. Cái phải biến mất là dấu
        # ngoặc mở thẻ.
        assert "<script>" not in content.html
        assert "&lt;script&gt;" in content.html
        assert "<img" not in content.html

    def test_du_thong_tin_khach_de_quyet_khong_can_mo_app(self) -> None:
        # Đây là lý do thư này tồn tại: đọc trên điện thoại là đủ để quyết có gọi lại ngay
        # không. Bản đầu chỉ có tên khách + tên dự án nên đọc xong vẫn phải mở laptop.
        content = build_new_deal_email(
            owner_name="A",
            client_name="Quán cà phê Nắng",
            project_name="Website bán hàng",
            deal_url="https://app.solodesk.space/deals/x",
            client_email="nang@cafe.vn",
            client_phone="0901234567",
            budget="30-50 triệu",
            timeline="Trong tháng 8",
            inquiry_text="Mình cần web bán cà phê rang xay, có giỏ hàng và thanh toán.",
            attachment_count=2,
        )
        for expected in ("nang@cafe.vn", "0901234567", "30-50 triệu", "Trong tháng 8"):
            assert expected in content.plain
            assert expected in content.html
        assert "2 tệp" in content.plain
        assert "rang xay" in content.plain

    def test_khong_co_tep_thi_khong_hien_dong_dinh_kem(self) -> None:
        content = build_new_deal_email(
            owner_name="A",
            client_name="Khách lẻ",
            project_name="X",
            deal_url="https://app.solodesk.space/deals/x",
            attachment_count=0,
        )
        assert "tệp" not in content.plain.lower()

    def test_trich_yeu_cau_dai_thi_cat_bot(self) -> None:
        # Thư không phải bản sao của trang chi tiết deal — dài quá thì mất tác dụng "liếc
        # một cái là hiểu".
        content = build_new_deal_email(
            owner_name="A",
            client_name="K",
            project_name="X",
            deal_url="https://app.solodesk.space/deals/x",
            inquiry_text="a" * 500,
        )
        assert "…" in content.plain
        assert "a" * 500 not in content.plain
