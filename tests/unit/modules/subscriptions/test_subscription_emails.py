"""Email vòng đời gói: sắp hết quota, sắp hết kỳ, đã hạ Free.

Nội dung này quyết định freelancer có biết gói mình sắp mất hay không, nên kiểm số liệu và
ngày tháng hiện đúng, và không vỡ khi tên chủ để trống.
"""

from datetime import UTC, datetime

from src.modules.subscriptions.application.emails import (
    build_downgrade_email,
    build_expiry_warning_email,
    build_quota_warning_email,
)

PERIOD_END = datetime(2026, 8, 20, tzinfo=UTC)


class TestQuotaWarningEmail:
    def test_hien_so_luot_da_dung_va_con_lai(self) -> None:
        content = build_quota_warning_email(
            owner_name="Chị Lan", used=40, limit=50, period_end=PERIOD_END
        )
        assert "40/50" in content.plain
        assert "20/08/2026" in content.plain
        assert "sắp hết" in content.subject.lower() or "hết lượt" in content.subject.lower()

    def test_thieu_ten_chu_van_on(self) -> None:
        content = build_quota_warning_email(
            owner_name=None, used=8, limit=10, period_end=PERIOD_END
        )
        assert "bạn" in content.plain


class TestExpiryWarningEmail:
    def test_hien_ten_goi_va_han(self) -> None:
        content = build_expiry_warning_email(
            owner_name="A", plan_name="Pro", period_end=PERIOD_END, days_left=3
        )
        assert "Pro" in content.subject
        assert "20/08/2026" in content.plain
        assert "3 ngày" in content.plain


class TestDowngradeEmail:
    def test_bao_da_chuyen_ve_free(self) -> None:
        content = build_downgrade_email(owner_name="A", plan_name="Pro")
        assert "Miễn phí" in content.plain
        assert "Pro" in content.plain
