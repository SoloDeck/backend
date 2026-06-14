"""Integration coverage for public intake placeholder route."""

from httpx import AsyncClient


async def test_public_intake_placeholder_returns_501_without_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/intake/not-yet", json={"inquiry_text": "Need a website"})
    assert resp.status_code == 501
    assert resp.json()["code"] == 501
