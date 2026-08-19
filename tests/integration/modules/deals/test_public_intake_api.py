"""Integration coverage for the public (unauthenticated) deal intake route.

POST /api/v1/intake/{share_token} — no auth. Verifies the happy path, bad-token
404, validation 422, and that the captured lead surfaces in the owner's GET /deals.
Uses real PostgreSQL (rolled back per test).
"""

import uuid
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from tests.integration.modules.clients.test_clients_api import _auth_headers


async def _owner_intake_token(client: AsyncClient) -> tuple[dict, str]:
    """Register an owner and return (auth_headers, intake_share_token)."""
    headers = await _auth_headers(client)
    me = await client.get("/api/v1/users/me", headers=headers)
    assert me.status_code == 200, me.text
    token = me.json()["data"]["intake_share_token"]
    assert token, "registration must mint an intake_share_token"
    return headers, token


async def test_public_intake_creates_lead_and_appears_in_owner_deals(client: AsyncClient) -> None:
    headers, token = await _owner_intake_token(client)

    with patch("src.workers.ai_jobs.tasks.qualify_deal_async_by_id.delay"):
        resp = await client.post(
            f"/api/v1/intake/{token}",
            json={
                "name": "Khách Hàng Mới",
                "email": "lead@example.com",
                "phone": "0900000000",
                "inquiry_text": "Cần thiết kế website bán hàng.",
                "estimated_budget": "20,000,000 VND",
                "desired_timeline": "1 tháng",
            },
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()["data"]
    assert "id" in body and "submitted_at" in body

    # The captured lead appears as a new_lead deal in the owner's pipeline.
    deals = await client.get("/api/v1/deals", headers=headers)
    assert deals.status_code == 200
    items = deals.json()["data"]
    assert any(d["stage"] == "new_lead" and "Khách Hàng Mới" in d["title"] for d in items)


async def test_public_intake_unknown_token_returns_404(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/intake/this-token-does-not-exist",
        json={"name": "Nobody", "inquiry_text": "Hello"},
    )
    assert resp.status_code == 404


async def test_public_intake_empty_body_returns_422(client: AsyncClient) -> None:
    _, token = await _owner_intake_token(client)
    resp = await client.post(f"/api/v1/intake/{token}", json={})
    assert resp.status_code == 422


async def test_public_intake_oversized_inquiry_returns_422(client: AsyncClient) -> None:
    _, token = await _owner_intake_token(client)
    resp = await client.post(
        f"/api/v1/intake/{token}",
        json={"name": "Lead", "inquiry_text": "x" * 5001},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Client deduplication
# ---------------------------------------------------------------------------


async def test_duplicate_intake_reuses_existing_client(client: AsyncClient) -> None:
    """Same name + phone → one client, two deals."""
    headers, token = await _owner_intake_token(client)

    payload = {"name": "Nguyen Van A", "phone": "0912345678", "inquiry_text": "First project"}

    with patch("src.workers.ai_jobs.tasks.qualify_deal_async_by_id.delay"):
        r1 = await client.post(f"/api/v1/intake/{token}", json=payload)
        r2 = await client.post(
            f"/api/v1/intake/{token}",
            json={**payload, "inquiry_text": "Second project"},
        )
    assert r1.status_code == 201
    assert r2.status_code == 201

    deals = await client.get("/api/v1/deals", headers=headers)
    all_deals = deals.json()["data"]
    client_ids = {d["client_id"] for d in all_deals}
    assert len(client_ids) == 1, "Both deals should belong to the same deduplicated client"
    assert len(all_deals) == 2, "Two separate deals should still be created"


async def test_different_phone_creates_new_client(client: AsyncClient) -> None:
    """Same name but different phone → two separate clients."""
    headers, token = await _owner_intake_token(client)

    with patch("src.workers.ai_jobs.tasks.qualify_deal_async_by_id.delay"):
        await client.post(
            f"/api/v1/intake/{token}",
            json={"name": "Tran Thi B", "phone": "0911111111", "inquiry_text": "First"},
        )
        await client.post(
            f"/api/v1/intake/{token}",
            json={"name": "Tran Thi B", "phone": "0922222222", "inquiry_text": "Second"},
        )

    deals = await client.get("/api/v1/deals", headers=headers)
    client_ids = {d["client_id"] for d in deals.json()["data"]}
    assert len(client_ids) == 2, "Different phones should create distinct clients"


async def test_duplicate_intake_client_deal_count_is_two(client: AsyncClient) -> None:
    """After two intakes from the same client, GET /clients shows deal_count == 2."""
    headers, token = await _owner_intake_token(client)

    payload = {"name": "Pham Thi D", "phone": "0933333333", "inquiry_text": "Project"}

    with patch("src.workers.ai_jobs.tasks.qualify_deal_async_by_id.delay"):
        await client.post(f"/api/v1/intake/{token}", json=payload)
        await client.post(
            f"/api/v1/intake/{token}",
            json={**payload, "inquiry_text": "Second project"},
        )

    clients_resp = await client.get("/api/v1/clients", headers=headers)
    assert clients_resp.status_code == 200
    items = clients_resp.json()["data"]
    assert len(items) == 1, "Only one deduplicated client should exist"
    assert items[0]["deal_count"] == 2, f"Expected deal_count=2, got {items[0]['deal_count']}"


async def test_no_phone_always_creates_new_client(client: AsyncClient) -> None:
    """No phone provided → always create a new client (cannot deduplicate safely)."""
    headers, token = await _owner_intake_token(client)

    with patch("src.workers.ai_jobs.tasks.qualify_deal_async_by_id.delay"):
        await client.post(
            f"/api/v1/intake/{token}",
            json={"name": "Le Van C", "inquiry_text": "First"},
        )
        await client.post(
            f"/api/v1/intake/{token}",
            json={"name": "Le Van C", "inquiry_text": "Second"},
        )

    deals = await client.get("/api/v1/deals", headers=headers)
    client_ids = {d["client_id"] for d in deals.json()["data"]}
    assert len(client_ids) == 2, "Without phone, two separate clients should be created"


# ---------------------------------------------------------------------------
# POST /api/v1/intake/{share_token}/{intake_id}/attachments
# ---------------------------------------------------------------------------


async def test_khach_gui_kem_tep_thi_freelancer_thay_trong_deal(client: AsyncClient) -> None:
    """Tệp khách kéo vào biểu mẫu phải tới được deal của freelancer.

    Trước đây form có khu kéo-thả và hứa nhận "PDF, Word, Excel, hình ảnh", nhưng phía gửi
    chỉ POST JSON — tệp bị vứt im lặng, khách tưởng đã gửi.  #Huynh
    """
    headers, token = await _owner_intake_token(client)

    with patch("src.workers.ai_jobs.tasks.qualify_deal_async_by_id.delay"):
        submit = await client.post(
            f"/api/v1/intake/{token}",
            json={"name": "Khách Có Tệp", "inquiry_text": "Brief đính kèm.", "attachment_count": 1},
        )
    assert submit.status_code == 201, submit.text
    intake_id = submit.json()["data"]["id"]

    # Kho file (MinIO) là dịch vụ NGOÀI — bài test này kiểm đường đi của tệp qua API và DB,
    # không kiểm MinIO. Chặn đúng một lệnh đẩy file, phần còn lại chạy thật.
    with (
        patch(
            "src.infrastructure.storage.object_storage.ObjectStorage.enabled",
            new=property(lambda self: True),
        ),
        patch(
            "src.infrastructure.storage.object_storage.ObjectStorage.upload",
            new=AsyncMock(return_value="deals/test/brief.pdf"),
        ),
    ):
        upload = await client.post(
            f"/api/v1/intake/{token}/{intake_id}/attachments",
            files={"file": ("brief.pdf", b"%PDF-1.4 noi dung brief", "application/pdf")},
        )
    assert upload.status_code == 201, upload.text
    assert upload.json()["data"]["filename"] == "brief.pdf"

    # Freelancer mở deal ra là thấy đúng tệp đó.
    deals = await client.get("/api/v1/deals", headers=headers)
    deal_id = next(d["id"] for d in deals.json()["data"] if "Khách Có Tệp" in d["title"])
    listed = await client.get(f"/api/v1/deals/{deal_id}/attachments", headers=headers)
    assert listed.status_code == 200, listed.text
    assert [a["filename"] for a in listed.json()["data"]] == ["brief.pdf"]


async def test_dinh_kem_bang_token_sai_thi_404(client: AsyncClient) -> None:
    _, token = await _owner_intake_token(client)

    with patch("src.workers.ai_jobs.tasks.qualify_deal_async_by_id.delay"):
        submit = await client.post(
            f"/api/v1/intake/{token}",
            json={"name": "Khách", "inquiry_text": "x", "attachment_count": 1},
        )
    intake_id = submit.json()["data"]["id"]

    # Có id phiếu thật nhưng link sai → không được ghi vào deal của người khác.
    resp = await client.post(
        f"/api/v1/intake/khong-ton-tai/{intake_id}/attachments",
        files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert resp.status_code == 404


async def test_gui_form_va_dinh_kem_bang_ten_duong_dan_rieng(client: AsyncClient) -> None:
    """Trang công khai mở được bằng token LẪN slug, nên hai đường GHI cũng phải nhận cả hai.

    Bản đầu chỉ dạy repository của `intake_form` tra slug; hai đường này đi qua
    `DealsRepository` nên vẫn chỉ nhận token — khách vào `/{slug}` gửi form là 404.
    """
    headers, _ = await _owner_intake_token(client)
    slug = f"thu-thuy-{uuid.uuid4().hex[:6]}"
    saved = await client.patch(
        "/api/v1/users/me/freelancer-profile", headers=headers, json={"profile_slug": slug}
    )
    assert saved.status_code == 200, saved.text

    with patch("src.workers.ai_jobs.tasks.qualify_deal_async_by_id.delay"):
        submit = await client.post(
            f"/api/v1/intake/{slug}",
            json={"name": "Khách Vào Bằng Slug", "inquiry_text": "Brief.", "attachment_count": 1},
        )
    assert submit.status_code == 201, submit.text
    intake_id = submit.json()["data"]["id"]

    with (
        patch(
            "src.infrastructure.storage.object_storage.ObjectStorage.enabled",
            new=property(lambda self: True),
        ),
        patch(
            "src.infrastructure.storage.object_storage.ObjectStorage.upload",
            new=AsyncMock(return_value="deals/test/brief.pdf"),
        ),
    ):
        upload = await client.post(
            f"/api/v1/intake/{slug}/{intake_id}/attachments",
            files={"file": ("brief.pdf", b"%PDF-1.4 noi dung", "application/pdf")},
        )
    assert upload.status_code == 201, upload.text

    deals = await client.get("/api/v1/deals", headers=headers)
    deal_id = next(d["id"] for d in deals.json()["data"] if "Khách Vào Bằng Slug" in d["title"])
    listed = await client.get(f"/api/v1/deals/{deal_id}/attachments", headers=headers)
    assert [a["filename"] for a in listed.json()["data"]] == ["brief.pdf"]
