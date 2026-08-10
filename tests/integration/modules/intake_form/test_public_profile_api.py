"""Integration tests for GET /api/v1/intake/{share_token}/profile.

Trang chia sẻ thay cho hồ sơ công khai tra theo user id của danh bạ cũ. Bài test đắt nhất
ở đây là `test_profile_does_not_leak_identifiers`: nó khoá đúng lý do trang này được đổi
cách định danh — không có id thì không dò được, không dò được thì không thành chợ.  #Huynh
"""

import uuid
from unittest.mock import patch

from httpx import AsyncClient


async def _auth(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"u_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Test@1234!",
            "full_name": "Test Freelancer",
        },
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _get_share_token(client: AsyncClient, headers: dict) -> str:
    resp = await client.get("/api/v1/users/me", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["intake_share_token"]


async def test_profile_returns_freelancer_for_valid_token(client: AsyncClient):
    headers = await _auth(client)
    token = await _get_share_token(client, headers)

    resp = await client.get(f"/api/v1/intake/{token}/profile")

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["full_name"] == "Test Freelancer"
    assert data["skills"] == []
    # Chưa cấu hình gì thì diện mạo để trống — giao diện tự rơi về gradient màu mặc định.
    assert data["cover_url"] is None
    assert data["brand_color"] is None


async def test_profile_needs_no_opt_in(client: AsyncClient):
    """Tài khoản vừa đăng ký, chưa bật cấu hình nào, vẫn có trang chia sẻ.

    Danh bạ cũ lọc `is_listed=True` nên 91/92 tài khoản không bao giờ hiện ra. Trang chia
    sẻ đi theo hướng ngược lại: freelancer nắm quyền qua việc phát link, không qua công tắc.
    """
    headers = await _auth(client)
    token = await _get_share_token(client, headers)

    resp = await client.get(f"/api/v1/intake/{token}/profile")

    assert resp.status_code == 200, resp.text


async def test_profile_does_not_leak_identifiers(client: AsyncClient):
    headers = await _auth(client)
    token = await _get_share_token(client, headers)

    resp = await client.get(f"/api/v1/intake/{token}/profile")

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    for leaked in ("id", "email", "phone", "intake_share_token"):
        assert leaked not in data, f"{leaked} không được lộ ra trang công khai"
    # Xếp hạng kiểu sàn: SoloDesk không chấm điểm freelancer, đừng để bò lại qua payload.
    for ranking in ("rating_average", "rating_count", "completed_project_count", "is_new"):
        assert ranking not in data, f"{ranking} là tín hiệu marketplace, đã bỏ"


async def test_profile_unknown_token_returns_404(client: AsyncClient):
    resp = await client.get(f"/api/v1/intake/{uuid.uuid4().hex}/profile")
    assert resp.status_code == 404


async def test_profile_reflects_cover_and_brand_color(client: AsyncClient):
    headers = await _auth(client)
    token = await _get_share_token(client, headers)

    saved = await client.patch(
        "/api/v1/users/me/freelancer-profile",
        headers=headers,
        json={"cover_url": "data:image/jpeg;base64,AAAA", "brand_color": "#0F766E"},
    )
    assert saved.status_code == 200, saved.text

    data = (await client.get(f"/api/v1/intake/{token}/profile")).json()["data"]
    assert data["cover_url"] == "data:image/jpeg;base64,AAAA"
    # Hex được chuẩn hoá về chữ thường lúc ghi, để so sánh ở FE khỏi phụ thuộc cách gõ.
    assert data["brand_color"] == "#0f766e"


async def test_brand_color_rejects_non_hex(client: AsyncClient):
    headers = await _auth(client)
    resp = await client.patch(
        "/api/v1/users/me/freelancer-profile", headers=headers, json={"brand_color": "red"}
    )
    assert resp.status_code == 422


async def test_blank_brand_color_clears_instead_of_failing(client: AsyncClient):
    """Chuỗi rỗng = bỏ màu, KHÔNG phải lỗi.

    Màn Cài đặt gửi mọi trường trong một lượt; nếu "" bị 422 thì người chưa chọn màu bấm Lưu
    là hỏng cả lượt lưu hồ sơ, y hệt lỗi số điện thoại trùng đã gặp trước đây.
    """
    headers = await _auth(client)
    resp = await client.patch(
        "/api/v1/users/me/freelancer-profile", headers=headers, json={"brand_color": ""}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["brand_color"] is None


async def test_cover_url_rejects_dangerous_scheme(client: AsyncClient):
    headers = await _auth(client)
    resp = await client.patch(
        "/api/v1/users/me/freelancer-profile",
        headers=headers,
        json={"cover_url": "javascript:alert(1)"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Tên đường dẫn riêng (profile_slug)
# ---------------------------------------------------------------------------


async def test_profile_reachable_by_slug(client: AsyncClient):
    headers = await _auth(client)
    token = await _get_share_token(client, headers)
    slug = f"thu-thuy-{uuid.uuid4().hex[:6]}"

    saved = await client.patch(
        "/api/v1/users/me/freelancer-profile", headers=headers, json={"profile_slug": slug}
    )
    assert saved.status_code == 200, saved.text

    by_slug = await client.get(f"/api/v1/intake/{slug}/profile")
    assert by_slug.status_code == 200, by_slug.text
    assert by_slug.json()["data"]["full_name"] == "Test Freelancer"

    # Link token cũ đã phát cho khách PHẢI còn chạy song song.
    by_token = await client.get(f"/api/v1/intake/{token}/profile")
    assert by_token.status_code == 200


async def test_slug_hoat_dong_tren_ca_ba_endpoint_cong_khai(client: AsyncClient):
    """Slug phải mở được trang, tải được cấu hình, VÀ gửi được form.

    Vì sao có bài này: bản đầu chỉ dạy repository của `intake_form` tra slug, còn đường
    GỬI form đi qua repository của `deals` thì không. Khách vào bằng `/{slug}` xem hồ sơ,
    thấy biểu mẫu, điền hết rồi bấm Gửi và ăn 404 — hỏng đúng bước chuyển đổi, mà hai
    endpoint đọc vẫn xanh nên không ai thấy. Bài test cũ dừng lại ngay TRƯỚC endpoint gửi.

    Vị từ tra cứu vì thế nằm ở hai repository và phải sửa cùng nhau; đây là chỗ khoá.
    """
    headers = await _auth(client)
    slug = f"nguyen-{uuid.uuid4().hex[:6]}"
    saved = await client.patch(
        "/api/v1/users/me/freelancer-profile", headers=headers, json={"profile_slug": slug}
    )
    assert saved.status_code == 200, saved.text

    profile = await client.get(f"/api/v1/intake/{slug}/profile")
    assert profile.status_code == 200, profile.text

    config = await client.get(f"/api/v1/intake/{slug}/config")
    assert config.status_code == 200, config.text
    assert config.json()["data"]["freelancer_name"] == "Test Freelancer"

    with patch("src.workers.ai_jobs.tasks.qualify_deal_async_by_id.delay"):
        submitted = await client.post(
            f"/api/v1/intake/{slug}",
            json={"name": "Khách Qua Đường Dẫn Riêng", "inquiry_text": "Cần làm web bán hàng."},
        )
    assert submitted.status_code == 201, submitted.text

    # Và lead phải thật sự về tới bảng deal của chủ, không chỉ là 201 suông.
    deals = await client.get("/api/v1/deals", headers=headers)
    assert any(
        d["stage"] == "new_lead" and "Khách Qua Đường Dẫn Riêng" in d["title"]
        for d in deals.json()["data"]
    ), deals.text


async def test_slug_conflict_returns_409_not_500(client: AsyncClient):
    slug = f"trung-ten-{uuid.uuid4().hex[:6]}"
    first = await _auth(client)
    assert (
        await client.patch(
            "/api/v1/users/me/freelancer-profile", headers=first, json={"profile_slug": slug}
        )
    ).status_code == 200

    second = await _auth(client)
    resp = await client.patch(
        "/api/v1/users/me/freelancer-profile", headers=second, json={"profile_slug": slug}
    )
    assert resp.status_code == 409, resp.text


async def test_slug_cua_tai_khoan_da_xoa_van_ra_409_chu_khong_phai_500(
    client: AsyncClient, db_session
):
    """Ràng buộc UNIQUE không loại hàng đã xoá mềm, nên bước kiểm cũng không được loại.

    Trước đây bước kiểm lọc `deleted_at IS NULL` còn ràng buộc thì không: kiểm báo "còn
    trống", `INSERT` xuống vỡ ràng buộc → 500 cho một việc rất bình thường.
    """
    from sqlalchemy import text

    slug = f"da-xoa-{uuid.uuid4().hex[:6]}"
    first = await _auth(client)
    assert (
        await client.patch(
            "/api/v1/users/me/freelancer-profile", headers=first, json={"profile_slug": slug}
        )
    ).status_code == 200

    # Xoá mềm THẲNG dưới DB — không gọi `DELETE /users/me`, vì endpoint đó nay nhả slug ra
    # và như vậy sẽ không dựng được đúng tình huống cần kiểm.
    await db_session.execute(
        text("UPDATE users SET deleted_at = now(), status = 'deleted' WHERE profile_slug = :s"),
        {"s": slug},
    )
    await db_session.flush()

    second = await _auth(client)
    resp = await client.patch(
        "/api/v1/users/me/freelancer-profile", headers=second, json={"profile_slug": slug}
    )
    assert resp.status_code == 409, resp.text


async def test_xoa_tai_khoan_thi_nguoi_khac_lay_duoc_ten_duong_dan(client: AsyncClient):
    slug = f"nha-ra-{uuid.uuid4().hex[:6]}"
    first = await _auth(client)
    assert (
        await client.patch(
            "/api/v1/users/me/freelancer-profile", headers=first, json={"profile_slug": slug}
        )
    ).status_code == 200
    assert (await client.delete("/api/v1/users/me", headers=first)).status_code in (200, 204)

    second = await _auth(client)
    resp = await client.patch(
        "/api/v1/users/me/freelancer-profile", headers=second, json={"profile_slug": slug}
    )
    assert resp.status_code == 200, resp.text


async def test_slug_rejects_system_route_names(client: AsyncClient):
    """Slug thành đường dẫn gốc, nên chiếm được 'login' là chiếm luôn màn đăng nhập."""
    headers = await _auth(client)
    for reserved in ("admin", "login", "api", "ho-so"):
        resp = await client.patch(
            "/api/v1/users/me/freelancer-profile",
            headers=headers,
            json={"profile_slug": reserved},
        )
        assert resp.status_code == 422, f"{reserved} phải bị từ chối: {resp.text}"


async def test_slug_rejects_bad_format(client: AsyncClient):
    headers = await _auth(client)
    for bad in ("Có Dấu", "-abc", "abc-", "ab", "a" * 33, "co khoang trang"):
        resp = await client.patch(
            "/api/v1/users/me/freelancer-profile", headers=headers, json={"profile_slug": bad}
        )
        assert resp.status_code == 422, f"{bad!r} phải bị từ chối: {resp.text}"


async def test_profile_cannot_be_fetched_by_user_id(client: AsyncClient):
    """Đưa user id vào chỗ share_token phải hỏng — id không mở được trang này."""
    headers = await _auth(client)
    me = await client.get("/api/v1/users/me", headers=headers)
    user_id = me.json()["data"]["id"]

    resp = await client.get(f"/api/v1/intake/{user_id}/profile")

    assert resp.status_code == 404


async def test_tat_cong_tac_thi_khach_khong_gui_duoc_nhung_van_xem_duoc_ho_so(
    client: AsyncClient,
):
    """Công tắc "Biểu mẫu đang hoạt động" phải chặn được THẬT.

    Trước đây `is_active` đi vòng qua `PUT /intake-form` rồi nằm im — không hàm nào phía công
    khai đọc nó, nên freelancer tắt đi mà khách vẫn gửi được như thường. Trang vẫn phải hiện
    hồ sơ (link đã phát cho khách không được thành trang lỗi), chỉ là không nhận yêu cầu nữa.
    """
    headers = await _auth(client)
    slug = f"tam-ngung-{uuid.uuid4().hex[:6]}"
    assert (
        await client.patch(
            "/api/v1/users/me/freelancer-profile", headers=headers, json={"profile_slug": slug}
        )
    ).status_code == 200

    saved = await client.put(
        "/api/v1/intake-form",
        headers=headers,
        json={
            "title": "Gửi yêu cầu dự án",
            "description": None,
            "is_active": False,
            "fields": [
                {
                    "field_key": "name",
                    "label": "Họ tên",
                    "placeholder": None,
                    "field_type": "text",
                    "is_required": True,
                    "is_visible": True,
                    "sort_order": 1,
                }
            ],
        },
    )
    assert saved.status_code == 200, saved.text

    # Hồ sơ vẫn mở được, và cấu hình công khai nói rõ đang tắt để giao diện thay chỗ biểu mẫu.
    assert (await client.get(f"/api/v1/intake/{slug}/profile")).status_code == 200
    config = await client.get(f"/api/v1/intake/{slug}/config")
    assert config.status_code == 200, config.text
    assert config.json()["data"]["is_active"] is False

    # Gọi thẳng API cũng không lách được.
    with patch("src.workers.ai_jobs.tasks.qualify_deal_async_by_id.delay"):
        blocked = await client.post(
            f"/api/v1/intake/{slug}",
            json={"name": "Khách Cố Gửi", "inquiry_text": "Cho mình hỏi."},
        )
    assert blocked.status_code == 422, blocked.text
