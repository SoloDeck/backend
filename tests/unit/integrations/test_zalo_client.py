"""Client Zalo OA — PKCE, chữ ký webhook, factory chọn real/mock, hành vi mock.

Phần gọi mạng (real) không test ở đây (cần app + URL công khai); mock + hàm thuần thì test
được trọn vẹn và là thứ chạy ở local.
"""

import base64
import hashlib
import types

from src.integrations.zalo.client import (
    MockZaloOAClient,
    RealZaloOAClient,
    code_challenge_for,
    generate_code_verifier,
    get_zalo_client,
    unusable_redirect_reason,
    verify_zalo_signature,
)


class TestPkce:
    def test_challenge_la_s256_cua_verifier(self) -> None:
        verifier = "khong-gian-ngau-nhien-123"
        expected = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        assert code_challenge_for(verifier) == expected

    def test_moi_lan_sinh_verifier_moi_khac_nhau(self) -> None:
        assert generate_code_verifier() != generate_code_verifier()


class TestChuKyWebhook:
    def test_chu_ky_dung_thi_pass(self) -> None:
        app_id, secret, ts = "app1", "sec1", "1699999999"
        body = b'{"timestamp":"1699999999","event_name":"follow"}'
        mac = hashlib.sha256(app_id.encode() + body + ts.encode() + secret.encode()).hexdigest()
        assert verify_zalo_signature(
            app_id=app_id, oa_secret=secret, raw_body=body, timestamp=ts, provided_mac=mac
        )

    def test_chu_ky_sai_thi_fail(self) -> None:
        assert not verify_zalo_signature(
            app_id="a", oa_secret="s", raw_body=b"{}", timestamp="1", provided_mac="deadbeef"
        )

    def test_thieu_du_lieu_thi_fail(self) -> None:
        assert not verify_zalo_signature(
            app_id="", oa_secret="s", raw_body=b"{}", timestamp="1", provided_mac="x"
        )


class TestFactory:
    def test_mac_dinh_la_mock(self) -> None:
        s = types.SimpleNamespace(zalo_mode="mock", zalo_oauth_redirect_uri="")
        assert isinstance(get_zalo_client(s), MockZaloOAClient)

    def test_real_khi_cau_hinh(self) -> None:
        s = types.SimpleNamespace(
            zalo_mode="real",
            zalo_app_id="a",
            zalo_app_secret="b",
            zalo_oauth_redirect_uri="https://x/cb",
        )
        assert isinstance(get_zalo_client(s), RealZaloOAClient)


class TestMockClient:
    def test_oauth_url_tro_ve_callback_kem_state_va_code(self) -> None:
        c = MockZaloOAClient(redirect_uri="http://be/api/v1/zalo/callback")
        url = c.build_oauth_url(state="st8", code_challenge="ch")
        assert "http://be/api/v1/zalo/callback" in url
        assert "state=st8" in url
        assert "code=" in url

    async def test_exchange_tra_token_va_send_ghi_lai(self) -> None:
        c = MockZaloOAClient(redirect_uri="")
        token = await c.exchange_code(code="x", code_verifier="v")
        assert token.access_token and token.refresh_token
        await c.send_cs_message(access_token="t", user_id="u1", text="chào")
        assert c.sent == [{"user_id": "u1", "text": "chào"}]


class TestRedirectUriDungDuocKhong:
    """Bắt trước những redirect URI mà Zalo CHẮC CHẮN từ chối.

    Zalo chỉ trả `error_code=-14003` trên một trang trắng, không nói domain nào sai. Ba ca
    dưới đây biết sai mà không cần hỏi Zalo, nên chặn tại máy chủ kèm lý do đọc được.
    """

    def test_domain_that_https_thi_dung_duoc(self) -> None:
        assert (
            unusable_redirect_reason("https://api-staging.solodesk.space/api/v1/zalo/callback")
            is None
        )

    def test_rong_thi_bao_chua_dat(self) -> None:
        assert unusable_redirect_reason("") == "chưa được đặt"
        assert unusable_redirect_reason("   ") == "chưa được đặt"

    def test_http_thuong_thi_bi_chan(self) -> None:
        reason = unusable_redirect_reason("http://api.solodesk.space/api/v1/zalo/callback")
        assert reason is not None and "https" in reason

    def test_localhost_thi_bi_chan(self) -> None:
        reason = unusable_redirect_reason("https://localhost:8000/api/v1/zalo/callback")
        assert reason is not None and "cục bộ" in reason

    def test_ngrok_thi_bi_chan(self) -> None:
        """Đúng URL đã chặn cả buổi thử hôm 24/07."""
        reason = unusable_redirect_reason(
            "https://unaccusable-whitley-intertribal.ngrok-free.dev/api/v1/zalo/callback"
        )
        assert reason is not None and "hầm tạm" in reason

    def test_domain_that_co_chuoi_ngrok_o_giua_thi_van_dung_duoc(self) -> None:
        """Chặn theo ĐUÔI domain, không phải chuỗi con — `ngrok.solodesk.space` là domain
        thật của mình, chặn nhầm là chặn oan."""
        assert unusable_redirect_reason("https://ngrok.solodesk.space/api/v1/zalo/callback") is None
