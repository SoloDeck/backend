"""Trường văn bản dài hơn cột Postgres phải bị chặn bằng 422, KHÔNG được rơi xuống DB thành 500.

Lỗi gốc: `POST /api/v1/deals` với `project_type` dài hơn 200 ký tự lọt qua schema (không có giới
hạn), tới Postgres thì nổ `StringDataRightTruncationError` → API trả 500 "An unexpected error
occurred". Cùng một lỗi nằm ở 7 trường nữa của deal, ở email/điện thoại/thành phố/quốc gia của
khách hàng (xem `tests/integration/modules/clients/test_field_length_limits.py`), ở `profession`
của biểu mẫu tiếp nhận CÔNG KHAI (không cần đăng nhập), và ở hai ô tiền (NUMERIC(15, 2)).

Mỗi trường được thử đúng hai điểm:
  * NGAY NGƯỠNG (= độ dài cột): phải tạo/sửa được và giá trị lưu ĐỦ, không bị cắt;
  * VƯỢT 1 ký tự: phải 422 kèm đúng tên trường và câu tiếng Việt nêu giới hạn.

Dùng PostgreSQL thật (rollback theo từng test) — chính DB mới là bên từ chối chuỗi quá dài, nên
mock DB ở đây là vô nghĩa.
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, Response

# (trường, độ dài cột trong DealModel, nhãn tiếng Việt phải có trong câu báo lỗi)
DEAL_TEXT_LIMITS = [
    ("title", 500, "Tên yêu cầu"),
    ("currency", 3, "Mã tiền tệ"),
    ("desired_timeline", 255, "Thời hạn khách nêu"),
    ("client_budget", 255, "Ngân sách khách nêu"),
    ("project_type", 200, "Loại dự án"),
    ("service_category", 200, "Nhóm dịch vụ"),
    ("pricing_tier", 100, "Mức giá"),
    ("profession", 100, "Nghề"),
]
_DEAL_IDS = [case[0] for case in DEAL_TEXT_LIMITS]

# Biểu mẫu tiếp nhận công khai: mọi trường chuỗi của `PublicIntakeRequest`.
INTAKE_TEXT_LIMITS = [
    ("name", 255, "Họ tên"),
    ("email", 255, "Email"),
    ("phone", 50, "Số điện thoại"),
    ("project_name", 500, "Tên dự án"),
    ("inquiry_text", 5000, "Nội dung yêu cầu"),
    ("estimated_budget", 255, "Ngân sách"),
    ("desired_timeline", 255, "Thời gian mong muốn"),
    ("profession", 100, "Nghề"),
]
_INTAKE_IDS = [case[0] for case in INTAKE_TEXT_LIMITS]

# NUMERIC(15, 2) → tối đa 13 chữ số nguyên.
MAX_MONEY = Decimal("9999999999999.99")
MAX_MONEY_TEXT = "9.999.999.999.999,99"


@pytest.fixture(autouse=True)
def _khong_gui_thu_va_khong_xep_hang_doi():
    """Luồng tiếp nhận công khai gửi thư báo + xếp lệnh chấm điểm AI vào Celery.

    Cả hai là phần phụ không liên quan tới việc kiểm giới hạn độ dài; chặn lại để test không
    chạm SMTP thật hay broker Redis dù biến môi trường có trỏ đi đâu.
    """
    with (
        patch("src.workers.ai_jobs.tasks.qualify_deal_async_by_id.delay"),
        patch("src.shared.email.smtp.send_email", new=AsyncMock()),
    ):
        yield


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


async def _create_client(client: AsyncClient, headers: dict) -> str:
    resp = await client.post("/api/v1/clients", json={"name": "Acme"}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _create_deal(client: AsyncClient, headers: dict) -> dict:
    client_id = await _create_client(client, headers)
    resp = await client.post(
        "/api/v1/deals", json={"client_id": client_id, "title": "Deal gốc"}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _assert_422_vuot_gioi_han(resp: Response, field: str, limit: int, label: str) -> None:
    """422 đúng khuôn: mã VALIDATION_FAILED, đúng trường, câu tiếng Việt nêu nhãn + giới hạn."""
    assert resp.status_code == 422, resp.text
    error = resp.json()["error"]
    assert error["code"] == "VALIDATION_FAILED"

    hits = [d for d in error["details"] if d["field"] == field]
    assert len(hits) == 1, error["details"]
    message = hits[0]["message"]
    assert label in message, message
    assert f"tối đa {limit} ký tự" in message, message
    assert f"bạn đã nhập {limit + 1}" in message, message
    # Câu mặc định của Pydantic là tiếng Anh và không nêu tên trường.
    assert "String should" not in message, message


# ---------------------------------------------------------------------------
# POST /deals
# ---------------------------------------------------------------------------


class TestTaoDeal:
    @pytest.mark.parametrize(("field", "limit", "_label"), DEAL_TEXT_LIMITS, ids=_DEAL_IDS)
    async def test_dung_nguong_tao_duoc_va_luu_du_chu(
        self, client: AsyncClient, field: str, limit: int, _label: str
    ) -> None:
        headers = await _register(client)
        client_id = await _create_client(client, headers)
        value = "x" * limit

        body = {"client_id": client_id, "title": "Deal", field: value}
        resp = await client.post("/api/v1/deals", json=body, headers=headers)

        assert resp.status_code == 201, resp.text
        assert resp.json()["data"][field] == value  # không bị cắt

    @pytest.mark.parametrize(("field", "limit", "label"), DEAL_TEXT_LIMITS, ids=_DEAL_IDS)
    async def test_vuot_nguong_mot_ky_tu_tra_422_khong_phai_500(
        self, client: AsyncClient, field: str, limit: int, label: str
    ) -> None:
        headers = await _register(client)
        client_id = await _create_client(client, headers)

        body = {"client_id": client_id, "title": "Deal", field: "x" * (limit + 1)}
        resp = await client.post("/api/v1/deals", json=body, headers=headers)

        _assert_422_vuot_gioi_han(resp, field, limit, label)

    async def test_ky_tu_co_dau_tinh_theo_ky_tu_khong_theo_byte(self, client: AsyncClient) -> None:
        """Cột VARCHAR(200) đếm KÝ TỰ. Chữ Việt có dấu chiếm 3 byte UTF-8 nhưng vẫn là 1 ký tự."""
        headers = await _register(client)
        client_id = await _create_client(client, headers)
        value = "ệ" * 200  # 600 byte, 200 ký tự

        resp = await client.post(
            "/api/v1/deals",
            json={"client_id": client_id, "title": "Deal", "project_type": value},
            headers=headers,
        )

        assert resp.status_code == 201, resp.text
        assert resp.json()["data"]["project_type"] == value

    async def test_nhieu_truong_cung_dai_thi_bao_het_mot_lan(self, client: AsyncClient) -> None:
        """Người dùng sửa một lượt, không phải sửa-gửi-lỗi-sửa-gửi từng trường một."""
        headers = await _register(client)
        client_id = await _create_client(client, headers)

        resp = await client.post(
            "/api/v1/deals",
            json={
                "client_id": client_id,
                "title": "Deal",
                "project_type": "x" * 201,
                "pricing_tier": "x" * 101,
            },
            headers=headers,
        )

        assert resp.status_code == 422
        fields = {d["field"] for d in resp.json()["error"]["details"]}
        assert fields == {"project_type", "pricing_tier"}


# ---------------------------------------------------------------------------
# PATCH /deals/{id}
# ---------------------------------------------------------------------------


class TestSuaDeal:
    @pytest.mark.parametrize(("field", "limit", "_label"), DEAL_TEXT_LIMITS, ids=_DEAL_IDS)
    async def test_dung_nguong_sua_duoc_va_luu_du_chu(
        self, client: AsyncClient, field: str, limit: int, _label: str
    ) -> None:
        headers = await _register(client)
        deal = await _create_deal(client, headers)
        value = "y" * limit

        resp = await client.patch(
            f"/api/v1/deals/{deal['id']}",
            json={"client_id": deal["client_id"], "title": deal["title"], field: value},
            headers=headers,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["data"][field] == value

    @pytest.mark.parametrize(("field", "limit", "label"), DEAL_TEXT_LIMITS, ids=_DEAL_IDS)
    async def test_vuot_nguong_mot_ky_tu_tra_422_khong_phai_500(
        self, client: AsyncClient, field: str, limit: int, label: str
    ) -> None:
        headers = await _register(client)
        deal = await _create_deal(client, headers)

        resp = await client.patch(
            f"/api/v1/deals/{deal['id']}",
            json={
                "client_id": deal["client_id"],
                "title": deal["title"],
                field: "y" * (limit + 1),
            },
            headers=headers,
        )

        _assert_422_vuot_gioi_han(resp, field, limit, label)

        # Bị từ chối thì deal giữ nguyên — không có bản ghi nửa vời.
        after = await client.get(f"/api/v1/deals/{deal['id']}", headers=headers)
        assert after.json()["data"][field] == deal[field]


# ---------------------------------------------------------------------------
# estimated_value / actual_value — NUMERIC(15, 2)
# ---------------------------------------------------------------------------


class TestGiaTriTien:
    @pytest.mark.parametrize("field", ["estimated_value", "actual_value"])
    async def test_dung_tran_cot_tao_duoc(self, client: AsyncClient, field: str) -> None:
        headers = await _register(client)
        client_id = await _create_client(client, headers)

        resp = await client.post(
            "/api/v1/deals",
            json={"client_id": client_id, "title": "Deal", field: str(MAX_MONEY)},
            headers=headers,
        )

        assert resp.status_code == 201, resp.text
        assert Decimal(resp.json()["data"][field]) == MAX_MONEY

    @pytest.mark.parametrize("field", ["estimated_value", "actual_value"])
    @pytest.mark.parametrize("value", [10**13, "10000000000000.00", "99999999999999999"])
    async def test_vuot_tran_cot_tra_422_khong_phai_500(
        self, client: AsyncClient, field: str, value: object
    ) -> None:
        headers = await _register(client)
        client_id = await _create_client(client, headers)

        resp = await client.post(
            "/api/v1/deals",
            json={"client_id": client_id, "title": "Deal", field: value},
            headers=headers,
        )

        assert resp.status_code == 422, resp.text
        error = resp.json()["error"]
        assert error["code"] == "VALIDATION_FAILED"
        hits = [d for d in error["details"] if d["field"] == field]
        assert len(hits) == 1, error["details"]
        assert "quá lớn" in hits[0]["message"]
        assert MAX_MONEY_TEXT in hits[0]["message"]

    async def test_gia_tri_am_van_bi_chan_nhu_cu(self, client: AsyncClient) -> None:
        """Không để giới hạn mới làm hỏng luật cũ (`ge=0`)."""
        headers = await _register(client)
        client_id = await _create_client(client, headers)

        resp = await client.post(
            "/api/v1/deals",
            json={"client_id": client_id, "title": "Deal", "estimated_value": -1},
            headers=headers,
        )

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /intake/{token} — biểu mẫu tiếp nhận CÔNG KHAI (không cần đăng nhập)
# ---------------------------------------------------------------------------


async def _owner_intake_token(client: AsyncClient) -> str:
    headers = await _register(client)
    me = await client.get("/api/v1/users/me", headers=headers)
    token = me.json()["data"]["intake_share_token"]
    assert token
    return token


class TestTiepNhanCongKhai:
    @pytest.mark.parametrize(("field", "limit", "_label"), INTAKE_TEXT_LIMITS, ids=_INTAKE_IDS)
    async def test_dung_nguong_gui_duoc(
        self, client: AsyncClient, field: str, limit: int, _label: str
    ) -> None:
        token = await _owner_intake_token(client)

        body = {"name": "Khách", "inquiry_text": "Cần làm website", field: "z" * limit}
        resp = await client.post(f"/api/v1/intake/{token}", json=body)

        assert resp.status_code == 201, resp.text

    @pytest.mark.parametrize(("field", "limit", "label"), INTAKE_TEXT_LIMITS, ids=_INTAKE_IDS)
    async def test_vuot_nguong_mot_ky_tu_tra_422_khong_phai_500(
        self, client: AsyncClient, field: str, limit: int, label: str
    ) -> None:
        token = await _owner_intake_token(client)

        body = {"name": "Khách", "inquiry_text": "Cần làm website", field: "z" * (limit + 1)}
        resp = await client.post(f"/api/v1/intake/{token}", json=body)

        _assert_422_vuot_gioi_han(resp, field, limit, label)

    async def test_profession_dai_khong_tao_ra_deal_nua_chung(self, client: AsyncClient) -> None:
        """`profession` là trường duy nhất của biểu mẫu công khai từng KHÔNG có giới hạn.

        Gửi vượt thì không được để lại client/deal dở dang trong DB của freelancer.
        """
        headers = await _register(client)
        me = await client.get("/api/v1/users/me", headers=headers)
        token = me.json()["data"]["intake_share_token"]

        resp = await client.post(
            f"/api/v1/intake/{token}",
            json={"name": "Khách", "inquiry_text": "Cần làm website", "profession": "p" * 101},
        )

        assert resp.status_code == 422
        deals = await client.get("/api/v1/deals", headers=headers)
        assert deals.json()["data"] == []
