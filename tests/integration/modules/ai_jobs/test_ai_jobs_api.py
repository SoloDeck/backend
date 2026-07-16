"""Integration tests for POST /api/v1/ai/jobs.

Uses real PostgreSQL (rolled back per test). The Celery `.delay()` calls are
patched out — there's no broker running in the test environment, and these
tests are about the job row / HTTP contract, not the worker itself (covered
separately by tests/unit/workers/test_ai_jobs_tasks.py and
tests/unit/modules/ai_jobs/).
"""

import uuid
from unittest.mock import patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import AiJobModel


def _reg(**overrides: object) -> dict:
    return {
        "email": f"user_{uuid.uuid4().hex[:8]}@example.com",
        "password": "Test@1234!",
        "full_name": "Test User",
        **overrides,
    }


async def _auth(client: AsyncClient) -> dict:
    resp = await client.post("/api/v1/auth/register", json=_reg())
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _create_client(http: AsyncClient, headers: dict) -> str:
    resp = await http.post(
        "/api/v1/clients", json={"name": "Acme Corp", "status": "prospect"}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _create_deal(http: AsyncClient, headers: dict, client_id: str) -> str:
    resp = await http.post(
        "/api/v1/deals", json={"title": "Test deal", "client_id": client_id}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _create_accepted_proposal(http: AsyncClient, headers: dict, deal_id: str) -> str:
    resp = await http.post(
        "/api/v1/proposals",
        json={"deal_id": deal_id, "content": {"body": "proposal body"}},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    pid = resp.json()["data"]["id"]
    await http.patch(f"/api/v1/proposals/{pid}/status", json={"status": "sent"}, headers=headers)
    r = await http.patch(
        f"/api/v1/proposals/{pid}/status", json={"status": "accepted"}, headers=headers
    )
    assert r.status_code == 200, r.text
    return pid


async def _create_contract(
    http: AsyncClient, headers: dict, deal_id: str, proposal_id: str, client_id: str
) -> str:
    resp = await http.post(
        "/api/v1/contracts",
        json={
            "deal_id": deal_id,
            "proposal_id": proposal_id,
            "client_id": client_id,
            "content": {"title": "Service Agreement"},
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _setup_deal(client: AsyncClient) -> tuple[dict, str]:
    headers = await _auth(client)
    client_id = await _create_client(client, headers)
    deal_id = await _create_deal(client, headers, client_id)
    return headers, deal_id


async def _setup_contract(client: AsyncClient) -> tuple[dict, str]:
    headers = await _auth(client)
    client_id = await _create_client(client, headers)
    deal_id = await _create_deal(client, headers, client_id)
    proposal_id = await _create_accepted_proposal(client, headers, deal_id)
    contract_id = await _create_contract(client, headers, deal_id, proposal_id, client_id)
    return headers, contract_id


class TestCreateJob:
    async def test_lead_qualifier_job_created(self, client: AsyncClient) -> None:
        headers, deal_id = await _setup_deal(client)

        with patch("src.workers.ai_jobs.tasks.qualify_deal_async_by_job_id.delay") as mock_delay:
            resp = await client.post(
                "/api/v1/ai/jobs",
                json={"type": "lead_qualifier", "entity_type": "deal", "entity_id": deal_id},
                headers=headers,
            )
        assert resp.status_code == 201, resp.text
        body = resp.json()["data"]
        assert body["type"] == "lead_qualifier"
        assert body["entity_type"] == "deal"
        assert body["entity_id"] == deal_id
        assert body["status"] == "queued"
        mock_delay.assert_called_once_with(body["id"])

    async def test_proposal_generator_job_created(self, client: AsyncClient) -> None:
        headers, deal_id = await _setup_deal(client)

        with patch("src.workers.ai_jobs.tasks.generate_proposal_async.delay") as mock_delay:
            resp = await client.post(
                "/api/v1/ai/jobs",
                json={"type": "proposal_generator", "entity_type": "deal", "entity_id": deal_id},
                headers=headers,
            )
        assert resp.status_code == 201, resp.text
        assert resp.json()["data"]["status"] == "queued"
        mock_delay.assert_called_once()

    async def test_contract_generator_job_created(self, client: AsyncClient) -> None:
        headers, contract_id = await _setup_contract(client)

        with patch("src.workers.ai_jobs.tasks.generate_contract_async.delay") as mock_delay:
            resp = await client.post(
                "/api/v1/ai/jobs",
                json={
                    "type": "contract_generator",
                    "entity_type": "contract",
                    "entity_id": contract_id,
                },
                headers=headers,
            )
        assert resp.status_code == 201, resp.text
        body = resp.json()["data"]
        assert body["entity_type"] == "contract"
        assert body["entity_id"] == contract_id
        mock_delay.assert_called_once()

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/ai/jobs",
            json={
                "type": "lead_qualifier",
                "entity_type": "deal",
                "entity_id": str(uuid.uuid4()),
            },
        )
        assert resp.status_code == 401

    async def test_invalid_type_returns_422(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.post(
            "/api/v1/ai/jobs",
            json={
                "type": "not_a_real_type",
                "entity_type": "deal",
                "entity_id": str(uuid.uuid4()),
            },
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_deal_not_found_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.post(
            "/api/v1/ai/jobs",
            json={
                "type": "lead_qualifier",
                "entity_type": "deal",
                "entity_id": str(uuid.uuid4()),
            },
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_tenant_isolation_deal_owned_by_other_user_returns_404(
        self, client: AsyncClient
    ) -> None:
        _, deal_id = await _setup_deal(client)
        other_headers = await _auth(client)

        resp = await client.post(
            "/api/v1/ai/jobs",
            json={"type": "lead_qualifier", "entity_type": "deal", "entity_id": deal_id},
            headers=other_headers,
        )
        assert resp.status_code == 404

    async def test_entity_type_mismatch_returns_409(self, client: AsyncClient) -> None:
        headers, deal_id = await _setup_deal(client)

        resp = await client.post(
            "/api/v1/ai/jobs",
            # contract_generator must target entity_type='contract', not 'deal'.
            json={"type": "contract_generator", "entity_type": "deal", "entity_id": deal_id},
            headers=headers,
        )
        assert resp.status_code == 409

    async def test_idempotency_key_returns_same_job_without_redispatch(
        self, client: AsyncClient
    ) -> None:
        headers, deal_id = await _setup_deal(client)
        body = {
            "type": "lead_qualifier",
            "entity_type": "deal",
            "entity_id": deal_id,
            "idempotency_key": "same-key-123",
        }

        with patch("src.workers.ai_jobs.tasks.qualify_deal_async_by_job_id.delay") as mock_delay:
            first = await client.post("/api/v1/ai/jobs", json=body, headers=headers)
            second = await client.post("/api/v1/ai/jobs", json=body, headers=headers)

        assert first.status_code == 201, first.text
        assert second.status_code == 201, second.text
        assert first.json()["data"]["id"] == second.json()["data"]["id"]
        mock_delay.assert_called_once()

    async def test_duplicate_active_job_without_idempotency_key_is_reused(
        self, client: AsyncClient
    ) -> None:
        headers, deal_id = await _setup_deal(client)
        body = {"type": "lead_qualifier", "entity_type": "deal", "entity_id": deal_id}

        with patch("src.workers.ai_jobs.tasks.qualify_deal_async_by_job_id.delay") as mock_delay:
            first = await client.post("/api/v1/ai/jobs", json=body, headers=headers)
            second = await client.post("/api/v1/ai/jobs", json=body, headers=headers)

        assert first.json()["data"]["id"] == second.json()["data"]["id"]
        mock_delay.assert_called_once()


class TestGetJob:
    async def test_get_returns_created_job(self, client: AsyncClient) -> None:
        headers, deal_id = await _setup_deal(client)
        with patch("src.workers.ai_jobs.tasks.qualify_deal_async_by_job_id.delay"):
            created = await client.post(
                "/api/v1/ai/jobs",
                json={"type": "lead_qualifier", "entity_type": "deal", "entity_id": deal_id},
                headers=headers,
            )
        job_id = created.json()["data"]["id"]

        resp = await client.get(f"/api/v1/ai/jobs/{job_id}", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["id"] == job_id
        assert body["status"] == "queued"
        assert body["result"] is None
        assert body["error"] is None

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/ai/jobs/{uuid.uuid4()}")
        assert resp.status_code == 401

    async def test_unknown_job_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.get(f"/api/v1/ai/jobs/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    async def test_tenant_isolation_returns_404_for_other_users_job(
        self, client: AsyncClient
    ) -> None:
        headers, deal_id = await _setup_deal(client)
        with patch("src.workers.ai_jobs.tasks.qualify_deal_async_by_job_id.delay"):
            created = await client.post(
                "/api/v1/ai/jobs",
                json={"type": "lead_qualifier", "entity_type": "deal", "entity_id": deal_id},
                headers=headers,
            )
        job_id = created.json()["data"]["id"]

        other_headers = await _auth(client)
        resp = await client.get(f"/api/v1/ai/jobs/{job_id}", headers=other_headers)
        assert resp.status_code == 404


class TestListJobs:
    async def test_list_returns_owned_jobs(self, client: AsyncClient) -> None:
        headers, deal_id = await _setup_deal(client)
        with patch("src.workers.ai_jobs.tasks.qualify_deal_async_by_job_id.delay"):
            created = await client.post(
                "/api/v1/ai/jobs",
                json={"type": "lead_qualifier", "entity_type": "deal", "entity_id": deal_id},
                headers=headers,
            )
        job_id = created.json()["data"]["id"]

        resp = await client.get("/api/v1/ai/jobs", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["pagination"]["total"] == 1
        assert any(j["id"] == job_id for j in body["data"])

    async def test_list_filters_by_entity(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        client_id = await _create_client(client, headers)
        deal_a = await _create_deal(client, headers, client_id)
        deal_b = await _create_deal(client, headers, client_id)

        with patch("src.workers.ai_jobs.tasks.qualify_deal_async_by_job_id.delay"):
            job_a = await client.post(
                "/api/v1/ai/jobs",
                json={"type": "lead_qualifier", "entity_type": "deal", "entity_id": deal_a},
                headers=headers,
            )
            await client.post(
                "/api/v1/ai/jobs",
                json={"type": "lead_qualifier", "entity_type": "deal", "entity_id": deal_b},
                headers=headers,
            )

        resp = await client.get(
            "/api/v1/ai/jobs",
            params={"entity_type": "deal", "entity_id": deal_a},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["pagination"]["total"] == 1
        assert body["data"][0]["id"] == job_a.json()["data"]["id"]

    async def test_list_does_not_leak_other_users_jobs(self, client: AsyncClient) -> None:
        headers, deal_id = await _setup_deal(client)
        with patch("src.workers.ai_jobs.tasks.qualify_deal_async_by_job_id.delay"):
            await client.post(
                "/api/v1/ai/jobs",
                json={"type": "lead_qualifier", "entity_type": "deal", "entity_id": deal_id},
                headers=headers,
            )

        other_headers = await _auth(client)
        resp = await client.get("/api/v1/ai/jobs", headers=other_headers)
        assert resp.status_code == 200
        assert resp.json()["pagination"]["total"] == 0

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/ai/jobs")
        assert resp.status_code == 401


class TestCancelJob:
    async def test_cancel_queued_job_succeeds(self, client: AsyncClient) -> None:
        headers, deal_id = await _setup_deal(client)
        with patch("src.workers.ai_jobs.tasks.qualify_deal_async_by_job_id.delay"):
            created = await client.post(
                "/api/v1/ai/jobs",
                json={"type": "lead_qualifier", "entity_type": "deal", "entity_id": deal_id},
                headers=headers,
            )
        job_id = created.json()["data"]["id"]

        resp = await client.post(f"/api/v1/ai/jobs/{job_id}/cancel", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "cancelled"

        # Cancellation persists.
        follow_up = await client.get(f"/api/v1/ai/jobs/{job_id}", headers=headers)
        assert follow_up.json()["data"]["status"] == "cancelled"

    async def test_cancel_terminal_job_returns_409(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers, deal_id = await _setup_deal(client)
        with patch("src.workers.ai_jobs.tasks.qualify_deal_async_by_job_id.delay"):
            created = await client.post(
                "/api/v1/ai/jobs",
                json={"type": "lead_qualifier", "entity_type": "deal", "entity_id": deal_id},
                headers=headers,
            )
        job_id = created.json()["data"]["id"]

        job = await db_session.get(AiJobModel, uuid.UUID(job_id))
        assert job is not None
        job.status = "succeeded"
        await db_session.flush()

        resp = await client.post(f"/api/v1/ai/jobs/{job_id}/cancel", headers=headers)
        assert resp.status_code == 409

    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        resp = await client.post(f"/api/v1/ai/jobs/{uuid.uuid4()}/cancel")
        assert resp.status_code == 401

    async def test_unknown_job_returns_404(self, client: AsyncClient) -> None:
        headers = await _auth(client)
        resp = await client.post(f"/api/v1/ai/jobs/{uuid.uuid4()}/cancel", headers=headers)
        assert resp.status_code == 404

    async def test_tenant_isolation_returns_404_for_other_users_job(
        self, client: AsyncClient
    ) -> None:
        headers, deal_id = await _setup_deal(client)
        with patch("src.workers.ai_jobs.tasks.qualify_deal_async_by_job_id.delay"):
            created = await client.post(
                "/api/v1/ai/jobs",
                json={"type": "lead_qualifier", "entity_type": "deal", "entity_id": deal_id},
                headers=headers,
            )
        job_id = created.json()["data"]["id"]

        other_headers = await _auth(client)
        resp = await client.post(f"/api/v1/ai/jobs/{job_id}/cancel", headers=other_headers)
        assert resp.status_code == 404
