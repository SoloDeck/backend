"""Integration tests for the intake form configuration endpoints."""

import uuid

from httpx import AsyncClient


async def _auth(client: AsyncClient) -> tuple[dict, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"u_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Test@1234!",
            "full_name": "Test Freelancer",
        },
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}, token


async def _get_share_token(client: AsyncClient, headers: dict) -> str:
    resp = await client.get("/api/v1/users/me", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["intake_share_token"]


# ---------------------------------------------------------------------------
# GET /api/v1/intake-form
# ---------------------------------------------------------------------------

async def test_get_form_returns_defaults_when_not_configured(client: AsyncClient):
    headers, _ = await _auth(client)
    resp = await client.get("/api/v1/intake-form", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] is None
    assert data["title"] == "Gửi yêu cầu dự án"
    assert data["is_active"] is True
    assert len(data["fields"]) == 7
    keys = [f["field_key"] for f in data["fields"]]
    assert "name" in keys
    assert "inquiry_text" in keys


async def test_get_form_returns_share_url(client: AsyncClient):
    headers, _ = await _auth(client)
    resp = await client.get("/api/v1/intake-form", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["share_url"] is not None


async def test_get_form_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/intake-form")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PUT /api/v1/intake-form
# ---------------------------------------------------------------------------

_SAMPLE_FIELDS = [
    {"field_key": "name", "label": "Full Name", "placeholder": "John Doe", "field_type": "text", "is_required": True, "is_visible": True, "sort_order": 1},
    {"field_key": "email", "label": "Email", "placeholder": None, "field_type": "email", "is_required": True, "is_visible": True, "sort_order": 2},
    {"field_key": "inquiry_text", "label": "Details", "placeholder": "Describe...", "field_type": "textarea", "is_required": True, "is_visible": True, "sort_order": 3},
]


async def test_put_creates_form_config(client: AsyncClient):
    headers, _ = await _auth(client)
    resp = await client.put(
        "/api/v1/intake-form",
        headers=headers,
        json={"title": "Project Inquiry", "description": "Tell us about your project", "is_active": True, "fields": _SAMPLE_FIELDS},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] is not None
    assert data["title"] == "Project Inquiry"
    assert data["description"] == "Tell us about your project"
    assert len(data["fields"]) == 3


async def test_put_then_get_returns_saved_config(client: AsyncClient):
    headers, _ = await _auth(client)
    await client.put(
        "/api/v1/intake-form",
        headers=headers,
        json={"title": "My Form", "description": None, "is_active": True, "fields": _SAMPLE_FIELDS},
    )
    resp = await client.get("/api/v1/intake-form", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["title"] == "My Form"
    assert len(data["fields"]) == 3


async def test_put_replaces_fields_on_second_save(client: AsyncClient):
    headers, _ = await _auth(client)
    await client.put(
        "/api/v1/intake-form",
        headers=headers,
        json={"title": "Form", "is_active": True, "fields": _SAMPLE_FIELDS},
    )
    new_fields = [{"field_key": "name", "label": "Name", "field_type": "text", "is_required": True, "is_visible": True, "sort_order": 1}]
    resp = await client.put(
        "/api/v1/intake-form",
        headers=headers,
        json={"title": "Updated", "is_active": True, "fields": new_fields},
    )
    assert resp.status_code == 200
    assert len(resp.json()["data"]["fields"]) == 1


async def test_put_tenant_isolation(client: AsyncClient):
    headers_a, _ = await _auth(client)
    headers_b, _ = await _auth(client)
    await client.put(
        "/api/v1/intake-form", headers=headers_a,
        json={"title": "User A Form", "is_active": True, "fields": _SAMPLE_FIELDS},
    )
    resp_b = await client.get("/api/v1/intake-form", headers=headers_b)
    assert resp_b.json()["data"]["title"] == "Gửi yêu cầu dự án"  # still default


async def test_put_requires_auth(client: AsyncClient):
    resp = await client.put(
        "/api/v1/intake-form",
        json={"title": "x", "is_active": True, "fields": []},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/intake/{share_token}/config
# ---------------------------------------------------------------------------

async def test_public_config_returns_defaults_when_not_configured(client: AsyncClient):
    headers, _ = await _auth(client)
    token = await _get_share_token(client, headers)
    resp = await client.get(f"/api/v1/intake/{token}/config")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["title"] == "Gửi yêu cầu dự án"
    assert data["freelancer_name"] == "Test Freelancer"
    assert len(data["fields"]) == 7


async def test_public_config_returns_saved_config(client: AsyncClient):
    headers, _ = await _auth(client)
    token = await _get_share_token(client, headers)
    await client.put(
        "/api/v1/intake-form", headers=headers,
        json={"title": "Custom Form", "description": "Hello", "is_active": True, "fields": _SAMPLE_FIELDS},
    )
    resp = await client.get(f"/api/v1/intake/{token}/config")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["title"] == "Custom Form"
    assert data["description"] == "Hello"
    assert len(data["fields"]) == 3


async def test_public_config_only_returns_visible_fields(client: AsyncClient):
    headers, _ = await _auth(client)
    token = await _get_share_token(client, headers)
    fields = [
        {"field_key": "name", "label": "Name", "field_type": "text", "is_required": True, "is_visible": True, "sort_order": 1},
        {"field_key": "phone", "label": "Phone", "field_type": "phone", "is_required": False, "is_visible": False, "sort_order": 2},
    ]
    await client.put("/api/v1/intake-form", headers=headers, json={"title": "F", "is_active": True, "fields": fields})
    resp = await client.get(f"/api/v1/intake/{token}/config")
    visible_keys = [f["field_key"] for f in resp.json()["data"]["fields"]]
    assert "name" in visible_keys
    assert "phone" not in visible_keys


async def test_public_config_invalid_token_returns_404(client: AsyncClient):
    resp = await client.get("/api/v1/intake/invalid-token-xyz/config")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/intake/{share_token} — required field validation
# ---------------------------------------------------------------------------

async def test_submit_validates_required_fields(client: AsyncClient):
    headers, _ = await _auth(client)
    token = await _get_share_token(client, headers)
    fields = [
        {"field_key": "name", "label": "Name", "field_type": "text", "is_required": True, "is_visible": True, "sort_order": 1},
        {"field_key": "inquiry_text", "label": "Details", "field_type": "textarea", "is_required": True, "is_visible": True, "sort_order": 2},
        {"field_key": "phone", "label": "Phone", "field_type": "phone", "is_required": True, "is_visible": True, "sort_order": 3},
    ]
    await client.put("/api/v1/intake-form", headers=headers, json={"title": "F", "is_active": True, "fields": fields})
    resp = await client.post(
        f"/api/v1/intake/{token}",
        json={"name": "Alice", "inquiry_text": "I need a website"},
    )
    assert resp.status_code == 422


async def test_submit_uses_project_name_as_deal_title(client: AsyncClient):
    headers, _ = await _auth(client)
    token = await _get_share_token(client, headers)
    fields = [
        {"field_key": "name", "label": "Name", "field_type": "text", "is_required": True, "is_visible": True, "sort_order": 1},
        {"field_key": "project_name", "label": "Project", "field_type": "text", "is_required": True, "is_visible": True, "sort_order": 2},
        {"field_key": "inquiry_text", "label": "Details", "field_type": "textarea", "is_required": False, "is_visible": True, "sort_order": 3},
    ]
    await client.put("/api/v1/intake-form", headers=headers, json={"title": "F", "is_active": True, "fields": fields})
    resp = await client.post(
        f"/api/v1/intake/{token}",
        json={"name": "Bob", "project_name": "Online Store"},
    )
    assert resp.status_code == 201
    deals = await client.get("/api/v1/deals", headers=headers)
    titles = [d["title"] for d in deals.json()["data"]]
    assert "Online Store" in titles


async def test_submit_falls_back_to_default_validation(client: AsyncClient):
    headers, _ = await _auth(client)
    token = await _get_share_token(client, headers)
    resp = await client.post(f"/api/v1/intake/{token}", json={"name": "Carol"})
    assert resp.status_code == 422


async def test_submit_succeeds_with_all_required_fields_present(client: AsyncClient):
    headers, _ = await _auth(client)
    token = await _get_share_token(client, headers)
    resp = await client.post(
        f"/api/v1/intake/{token}",
        json={"name": "Dave", "inquiry_text": "Need a logo"},
    )
    assert resp.status_code == 201
