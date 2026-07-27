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
        assert content.subject == "[SoloDesk] Deal mới từ Quán cà phê Nắng"

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
        )
        assert "<script>" not in content.html
        assert "&lt;script&gt;" in content.html
