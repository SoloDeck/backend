"""Trường văn bản của khách hàng dài hơn cột Postgres phải bị chặn bằng 422, KHÔNG phải 500.

Chỉ `name` từng có `max_length`. Email (255), số điện thoại (50), thành phố và quốc gia (100)
lọt qua schema, tới Postgres thì nổ `StringDataRightTruncationError` → API trả 500 "An unexpected
error occurred". Cùng họ lỗi với `POST /deals` có `project_type` dài hơn 200 ký tự — xem
`tests/integration/modules/deals/test_field_length_limits.py`.

Mỗi trường được thử đúng hai điểm, ở CẢ tạo (POST) lẫn sửa (PATCH):
  * NGAY NGƯỠNG (= độ dài cột): phải lưu được và lưu ĐỦ, không bị cắt;
  * VƯỢT 1 ký tự: phải 422 kèm đúng tên trường và câu tiếng Việt nêu giới hạn.

Dùng PostgreSQL thật (rollback theo từng test): chính DB mới là bên từ chối chuỗi quá dài.
"""

import uuid

import pytest
from httpx import AsyncClient, Response

# (trường, độ dài cột trong ClientModel, nhãn tiếng Việt phải có trong câu báo lỗi)
CLIENT_TEXT_LIMITS = [
    ("name", 255, "Tên khách hàng"),
    ("email", 255, "Email"),
    ("phone", 50, "Số điện thoại"),
    ("address_city", 100, "Thành phố"),
    ("address_country", 100, "Quốc gia"),
]
_IDS = [case[0] for case in CLIENT_TEXT_LIMITS]


async def _register(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"u_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Test@1234!",
            "full_name": "Test User",
        },
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _create_client(client: AsyncClient, headers: dict) -> dict:
    resp = await client.post("/api/v1/clients", json={"name": "Acme"}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _assert_422_vuot_gioi_han(resp: Response, field: str, limit: int, label: str) -> None:
    assert resp.status_code == 422, resp.text
    error = resp.json()["error"]
    assert error["code"] == "VALIDATION_FAILED"

    hits = [d for d in error["details"] if d["field"] == field]
    assert len(hits) == 1, error["details"]
    message = hits[0]["message"]
    assert label in message, message
    assert f"tối đa {limit} ký tự" in message, message
    assert f"bạn đã nhập {limit + 1}" in message, message
    assert "String should" not in message, message  # câu tiếng Anh mặc định của Pydantic


class TestTaoKhachHang:
    @pytest.mark.parametrize(("field", "limit", "_label"), CLIENT_TEXT_LIMITS, ids=_IDS)
    async def test_dung_nguong_tao_duoc_va_luu_du_chu(
        self, client: AsyncClient, field: str, limit: int, _label: str
    ) -> None:
        headers = await _register(client)
        value = "x" * limit

        resp = await client.post(
            "/api/v1/clients", json={"name": "Acme", field: value}, headers=headers
        )

        assert resp.status_code == 201, resp.text
        assert resp.json()["data"][field] == value  # không bị cắt

    @pytest.mark.parametrize(("field", "limit", "label"), CLIENT_TEXT_LIMITS, ids=_IDS)
    async def test_vuot_nguong_mot_ky_tu_tra_422_khong_phai_500(
        self, client: AsyncClient, field: str, limit: int, label: str
    ) -> None:
        headers = await _register(client)

        resp = await client.post(
            "/api/v1/clients", json={"name": "Acme", field: "x" * (limit + 1)}, headers=headers
        )

        _assert_422_vuot_gioi_han(resp, field, limit, label)

    async def test_nhieu_truong_cung_dai_thi_bao_het_mot_lan(self, client: AsyncClient) -> None:
        headers = await _register(client)

        resp = await client.post(
            "/api/v1/clients",
            json={"name": "Acme", "email": "e" * 256, "phone": "9" * 51},
            headers=headers,
        )

        assert resp.status_code == 422
        fields = {d["field"] for d in resp.json()["error"]["details"]}
        assert fields == {"email", "phone"}


class TestSuaKhachHang:
    @pytest.mark.parametrize(("field", "limit", "_label"), CLIENT_TEXT_LIMITS, ids=_IDS)
    async def test_dung_nguong_sua_duoc_va_luu_du_chu(
        self, client: AsyncClient, field: str, limit: int, _label: str
    ) -> None:
        headers = await _register(client)
        created = await _create_client(client, headers)
        value = "y" * limit

        resp = await client.patch(
            f"/api/v1/clients/{created['id']}", json={field: value}, headers=headers
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["data"][field] == value

    @pytest.mark.parametrize(("field", "limit", "label"), CLIENT_TEXT_LIMITS, ids=_IDS)
    async def test_vuot_nguong_mot_ky_tu_tra_422_khong_phai_500(
        self, client: AsyncClient, field: str, limit: int, label: str
    ) -> None:
        headers = await _register(client)
        created = await _create_client(client, headers)

        resp = await client.patch(
            f"/api/v1/clients/{created['id']}", json={field: "y" * (limit + 1)}, headers=headers
        )

        _assert_422_vuot_gioi_han(resp, field, limit, label)

        # Bị từ chối thì hồ sơ khách giữ nguyên.
        after = await client.get(f"/api/v1/clients/{created['id']}", headers=headers)
        assert after.json()["data"][field] == created[field]
