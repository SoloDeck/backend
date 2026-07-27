"""Template lời nhắc tự soạn.

Nội dung này gửi tới khách hàng thật, nên hai thứ được phủ kỹ: thay đúng placeholder, và
một dấu `{` lạc trong nội dung freelancer gõ KHÔNG được làm cả lượt quét đổ vỡ.
"""

from src.modules.reminders.domain.value_objects.reminder_rules import (
    RULE_DEFAULTS,
    VARIABLE_LABELS,
    RuleType,
    effective_template,
    render_reminder_template,
)


class TestRenderTemplate:
    def test_thay_placeholder(self) -> None:
        out = render_reminder_template(
            "Chào {client_name}, dự án {deal_title} nhé.",
            {"client_name": "Anh Nam", "deal_title": "Website bán hàng"},
        )
        assert out == "Chào Anh Nam, dự án Website bán hàng nhé."

    def test_placeholder_lap_lai_deu_duoc_thay(self) -> None:
        out = render_reminder_template(
            "{client_name} ơi, {client_name} nhé", {"client_name": "Lan"}
        )
        assert out == "Lan ơi, Lan nhé"

    def test_dau_ngoac_lac_khong_lam_do_vo(self) -> None:
        """`str.format` sẽ ném KeyError ở đây — thay chuỗi tường minh thì không."""
        out = render_reminder_template(
            "Giảm giá {50%} cho {client_name}", {"client_name": "Hoa"}
        )
        assert out == "Giảm giá {50%} cho Hoa"

    def test_bien_khong_co_trong_template_thi_bo_qua(self) -> None:
        out = render_reminder_template("Chào {client_name}", {"client_name": "An", "amount": "1đ"})
        assert out == "Chào An"


class TestEffectiveTemplate:
    def test_bo_trong_thi_dung_mac_dinh(self) -> None:
        for message_template in (None, "", "   \n  "):
            assert (
                effective_template(RuleType.PROPOSAL_FOLLOW_UP, message_template)
                == RULE_DEFAULTS[RuleType.PROPOSAL_FOLLOW_UP].default_template
            )

    def test_co_ban_tu_soan_thi_uu_tien(self) -> None:
        assert effective_template(RuleType.PAYMENT_DUE, "Nhắc {client_name} nhé") == (
            "Nhắc {client_name} nhé"
        )


class TestRuleDefaults:
    def test_moi_quy_tac_co_template_va_bien_hop_le(self) -> None:
        for rule_type, spec in RULE_DEFAULTS.items():
            assert spec.default_template.strip(), rule_type
            assert spec.variables, rule_type
            # Mọi biến khai báo đều có nhãn tiếng Việt và xuất hiện trong template mặc định.
            for name in spec.variables:
                assert name in VARIABLE_LABELS, (rule_type, name)
                assert "{" + name + "}" in spec.default_template, (rule_type, name)
