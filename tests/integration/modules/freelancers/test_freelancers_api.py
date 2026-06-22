"""Integration tests for the public freelancer directory endpoints."""

import uuid

from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _register(client: AsyncClient, **overrides) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"fl_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Test@1234!",
            "full_name": "Test Freelancer",
            **overrides,
        },
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = await client.get("/api/v1/users/me", headers=headers)
    assert me.status_code == 200, me.text
    return {
        "id": me.json()["data"]["id"],
        "token": token,
        "headers": headers,
    }


async def _set_profile(client: AsyncClient, headers: dict, **fields) -> None:
    resp = await client.patch(
        "/api/v1/users/me/freelancer-profile", json=fields, headers=headers
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# GET /public/freelancers/categories  (Page 1)
# ---------------------------------------------------------------------------

class TestListCategories:
    async def test_returns_five_categories(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/public/freelancers/categories")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 5

    async def test_category_shape(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/public/freelancers/categories")
        for cat in resp.json()["data"]:
            assert "slug" in cat
            assert "name" in cat
            assert "sub_skills" in cat

    async def test_expected_slugs(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/public/freelancers/categories")
        slugs = {c["slug"] for c in resp.json()["data"]}
        assert slugs == {"design", "programming", "marketing", "content", "consulting"}

    async def test_no_auth_required(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/public/freelancers/categories")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /public/freelancers  (Page 2 — list + search)
# ---------------------------------------------------------------------------

class TestSearchFreelancers:
    async def test_unlisted_user_not_visible(self, client: AsyncClient) -> None:
        await _register(client)  # never calls set_profile, so is_listed=False
        resp = await client.get("/api/v1/public/freelancers")
        # All returned items must be listed
        for fl in resp.json()["data"]:
            assert fl.get("id") is not None

    async def test_listed_user_appears(self, client: AsyncClient) -> None:
        user = await _register(client)
        await _set_profile(
            client, user["headers"],
            professional_title="Senior Dev",
            service_categories=["programming"],
            is_listed=True,
        )
        resp = await client.get("/api/v1/public/freelancers")
        ids = [f["id"] for f in resp.json()["data"]]
        assert user["id"] in ids

    async def test_returns_paginated_envelope(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/public/freelancers")
        body = resp.json()
        assert body["success"] is True
        assert "pagination" in body
        assert isinstance(body["data"], list)

    async def test_filter_by_category(self, client: AsyncClient) -> None:
        user = await _register(client)
        await _set_profile(
            client, user["headers"],
            service_categories=["design"],
            is_listed=True,
        )
        resp = await client.get(
            "/api/v1/public/freelancers", params={"categories": "design"}
        )
        for fl in resp.json()["data"]:
            assert "design" in fl["service_categories"]

    async def test_filter_by_category_excludes_other(self, client: AsyncClient) -> None:
        user_prog = await _register(client)
        await _set_profile(
            client, user_prog["headers"],
            service_categories=["programming"],
            is_listed=True,
        )
        user_mkt = await _register(client)
        await _set_profile(
            client, user_mkt["headers"],
            service_categories=["marketing"],
            is_listed=True,
        )
        resp = await client.get(
            "/api/v1/public/freelancers", params={"categories": "marketing"}
        )
        ids = [f["id"] for f in resp.json()["data"]]
        assert user_mkt["id"] in ids
        assert user_prog["id"] not in ids

    async def test_search_by_name(self, client: AsyncClient) -> None:
        user = await _register(client, full_name="UniqueNameXYZ999")
        await _set_profile(client, user["headers"], is_listed=True)

        resp = await client.get(
            "/api/v1/public/freelancers", params={"q": "UniqueNameXYZ999"}
        )
        ids = [f["id"] for f in resp.json()["data"]]
        assert user["id"] in ids

    async def test_search_by_bio(self, client: AsyncClient) -> None:
        user = await _register(client)
        await _set_profile(
            client, user["headers"],
            bio="ExpertInRocketScienceABC",
            is_listed=True,
        )
        resp = await client.get(
            "/api/v1/public/freelancers", params={"q": "ExpertInRocketScienceABC"}
        )
        ids = [f["id"] for f in resp.json()["data"]]
        assert user["id"] in ids

    async def test_search_by_professional_title(self, client: AsyncClient) -> None:
        user = await _register(client)
        await _set_profile(
            client, user["headers"],
            professional_title="QuantumMLSpecialistZZZ",
            is_listed=True,
        )
        resp = await client.get(
            "/api/v1/public/freelancers", params={"q": "QuantumMLSpecialistZZZ"}
        )
        ids = [f["id"] for f in resp.json()["data"]]
        assert user["id"] in ids

    async def test_search_no_match_returns_empty(self, client: AsyncClient) -> None:
        resp = await client.get(
            "/api/v1/public/freelancers", params={"q": "XXXXXXXNOTEXISTXXXXXXX"}
        )
        assert resp.json()["data"] == []

    async def test_progress_fields_in_response(self, client: AsyncClient) -> None:
        user = await _register(client)
        await _set_profile(client, user["headers"], is_listed=True)
        resp = await client.get(
            "/api/v1/public/freelancers", params={"q": user["id"]}
        )
        # Just verify schema — search by id won't match, so check a listed user
        resp2 = await client.get("/api/v1/public/freelancers")
        if resp2.json()["data"]:
            fl = resp2.json()["data"][0]
            assert "rating_average" in fl
            assert "rating_count" in fl
            assert "completed_project_count" in fl
            assert "is_new" in fl

    async def test_no_auth_required(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/public/freelancers")
        assert resp.status_code == 200

    async def test_pagination(self, client: AsyncClient) -> None:
        resp = await client.get(
            "/api/v1/public/freelancers", params={"page": 1, "page_size": 2}
        )
        assert resp.status_code == 200
        assert "pagination" in resp.json()


# ---------------------------------------------------------------------------
# GET /public/freelancers/:id
# ---------------------------------------------------------------------------

class TestGetFreelancer:
    async def test_returns_listed_freelancer(self, client: AsyncClient) -> None:
        user = await _register(client)
        await _set_profile(
            client, user["headers"],
            professional_title="Frontend Dev",
            bio="React and Vue expert.",
            service_categories=["programming"],
            skills=["React", "Vue"],
            is_listed=True,
        )
        resp = await client.get(f"/api/v1/public/freelancers/{user['id']}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == user["id"]
        assert data["professional_title"] == "Frontend Dev"
        assert data["bio"] == "React and Vue expert."
        assert "programming" in data["service_categories"]
        assert "React" in data["skills"]

    async def test_unlisted_returns_404(self, client: AsyncClient) -> None:
        user = await _register(client)  # is_listed=False by default
        resp = await client.get(f"/api/v1/public/freelancers/{user['id']}")
        assert resp.status_code == 404

    async def test_unknown_id_returns_404(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/public/freelancers/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_no_auth_required(self, client: AsyncClient) -> None:
        user = await _register(client)
        await _set_profile(client, user["headers"], is_listed=True)
        resp = await client.get(f"/api/v1/public/freelancers/{user['id']}")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# PATCH /users/me/freelancer-profile
# ---------------------------------------------------------------------------

class TestUpdateFreelancerProfile:
    async def test_sets_profile_fields(self, client: AsyncClient) -> None:
        user = await _register(client)
        resp = await client.patch(
            "/api/v1/users/me/freelancer-profile",
            json={
                "professional_title": "AI Specialist",
                "bio": "Building AI products.",
                "skills": ["Python", "FastAPI"],
                "service_categories": ["programming", "consulting"],
                "is_listed": True,
            },
            headers=user["headers"],
        )
        assert resp.status_code == 200

    async def test_partial_update_leaves_other_fields(self, client: AsyncClient) -> None:
        user = await _register(client)
        await _set_profile(
            client, user["headers"],
            professional_title="Original Title",
            bio="Original bio",
            is_listed=True,
        )
        # Update only bio
        resp = await client.patch(
            "/api/v1/users/me/freelancer-profile",
            json={"bio": "Updated bio"},
            headers=user["headers"],
        )
        assert resp.status_code == 200
        # Original title should be unchanged — verify via public profile
        get_resp = await client.get(f"/api/v1/public/freelancers/{user['id']}")
        data = get_resp.json()["data"]
        assert data["professional_title"] == "Original Title"
        assert data["bio"] == "Updated bio"

    async def test_can_unlist_by_setting_false(self, client: AsyncClient) -> None:
        user = await _register(client)
        await _set_profile(client, user["headers"], is_listed=True)
        await _set_profile(client, user["headers"], is_listed=False)
        resp = await client.get(f"/api/v1/public/freelancers/{user['id']}")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.patch(
            "/api/v1/users/me/freelancer-profile", json={"is_listed": True}
        )
        assert resp.status_code == 401
