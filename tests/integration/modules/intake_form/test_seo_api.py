"""Integration tests cho hai route SEO: /internal/render/profile/{slug} và /sitemap.xml."""

import uuid

from httpx import AsyncClient

from src.config.settings import settings


async def _auth(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"u_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Test@1234!",
            "full_name": "Thu Thủy",
        },
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _with_slug(client: AsyncClient, headers: dict, **profile) -> str:
    slug = f"thu-thuy-{uuid.uuid4().hex[:6]}"
    resp = await client.patch(
        "/api/v1/users/me/freelancer-profile",
        headers=headers,
        json={"profile_slug": slug, **profile},
    )
    assert resp.status_code == 200, resp.text
    return slug


def _base() -> str:
    return settings.frontend_url.rstrip("/")


async def test_render_profile_emits_meta_tags(client: AsyncClient):
    headers = await _auth(client)
    slug = await _with_slug(
        client,
        headers,
        bio="Thiết kế thương hiệu cho doanh nghiệp nhỏ tại Việt Nam.",
        professional_title="Nhà thiết kế thương hiệu",
    )

    resp = await client.get(f"/internal/render/profile/{slug}")

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/html")
    html = resp.text
    assert "<title>Thu Thủy — SoloDesk</title>" in html
    assert 'name="description" content="Thiết kế thương hiệu' in html
    assert 'property="og:type" content="profile"' in html
    assert f'property="og:url" content="{_base()}/{slug}"' in html
    assert 'property="og:image"' in html
    assert 'name="twitter:card" content="summary_large_image"' in html
    assert 'type="application/ld+json"' in html
    assert '"@type":"Person"' in html
    assert f'<link rel="canonical" href="{_base()}/{slug}">' in html
    # Body không được rỗng — trang rỗng vẫn bị xếp là nội dung mỏng.
    assert "<h1>Thu Th" in html


async def test_render_profile_unknown_slug_returns_404_noindex(client: AsyncClient):
    resp = await client.get(f"/internal/render/profile/khong-co-{uuid.uuid4().hex[:6]}")

    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("text/html")
    assert 'name="robots" content="noindex' in resp.text


async def test_render_profile_escapes_user_content(client: AsyncClient):
    """Bio là dữ liệu freelancer tự nhập và trang này ai cũng mở được."""
    headers = await _auth(client)
    slug = await _with_slug(client, headers, bio='</script><script>alert(1)</script>"onload="x')

    html = (await client.get(f"/internal/render/profile/{slug}")).text

    assert "<script>alert(1)</script>" not in html
    assert "</script><script>" not in html


async def test_sitemap_lists_home_and_public_profiles(client: AsyncClient):
    headers = await _auth(client)
    slug = await _with_slug(client, headers)

    resp = await client.get("/sitemap.xml")

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/xml")
    xml = resp.text
    assert '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' in xml
    assert f"<loc>{_base()}/home</loc>" in xml
    assert f"<loc>{_base()}/{slug}</loc>" in xml
    assert "<lastmod>" in xml


async def test_sitemap_omits_profiles_without_slug(client: AsyncClient):
    """Link token 43 ký tự cố ý không dò được — đưa vào sitemap là phá đúng tính chất đó."""
    headers = await _auth(client)
    token = (await client.get("/api/v1/users/me", headers=headers)).json()["data"][
        "intake_share_token"
    ]

    xml = (await client.get("/sitemap.xml")).text

    assert token not in xml
