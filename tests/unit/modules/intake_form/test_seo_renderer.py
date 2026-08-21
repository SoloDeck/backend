"""Unit tests cho lớp render trang SEO — cắt mô tả, thoát dữ liệu, dựng sitemap."""

import json
from datetime import UTC, datetime

from src.modules.intake_form.application import seo_renderer


def test_mo_ta_ngan_giu_nguyen():
    assert seo_renderer.truncate_description("Thiết kế logo.", fallback="x") == "Thiết kế logo."


def test_mo_ta_rong_dung_fallback():
    assert seo_renderer.truncate_description(None, fallback="Hồ sơ freelancer") == (
        "Hồ sơ freelancer"
    )
    assert seo_renderer.truncate_description("   \n  ", fallback="Hồ sơ") == "Hồ sơ"


def test_mo_ta_dai_bi_cat_o_ranh_gioi_tu():
    text = "sanpham " * 40
    result = seo_renderer.truncate_description(text, fallback="x")
    assert len(result) <= 160
    assert result.endswith("…")
    assert not result.rstrip("…").endswith(" ")


def test_mo_ta_gop_xuong_dong_thanh_mot_dong():
    assert seo_renderer.truncate_description("dòng 1\n\n dòng 2", fallback="x") == "dòng 1 dòng 2"


def _render(**overrides) -> str:
    kwargs = {
        "full_name": "Thu Thủy",
        "professional_title": "Nhà thiết kế",
        "description": "Thiết kế thương hiệu.",
        "image_url": "https://cdn.example/a.png",
        "canonical_url": "https://solodesk.space/thu-thuy",
        "skills": ["Logo"],
    }
    return seo_renderer.render_profile_page(**{**kwargs, **overrides})


def test_trang_ho_so_co_du_the_meta():
    html = _render()
    for fragment in (
        "<title>Thu Thủy — SoloDesk</title>",
        'name="description" content="Thiết kế thương hiệu."',
        'property="og:type" content="profile"',
        'property="og:url" content="https://solodesk.space/thu-thuy"',
        'property="og:image" content="https://cdn.example/a.png"',
        'name="twitter:card" content="summary_large_image"',
        '<link rel="canonical" href="https://solodesk.space/thu-thuy">',
    ):
        assert fragment in html, fragment


def test_json_ld_parse_duoc_va_dung_schema_person():
    html = _render()
    raw = html.split('<script type="application/ld+json">')[1].split("</script>")[0]
    data = json.loads(raw)
    assert data["@type"] == "ProfilePage"
    assert data["mainEntity"]["@type"] == "Person"
    assert data["mainEntity"]["name"] == "Thu Thủy"
    assert data["mainEntity"]["url"] == "https://solodesk.space/thu-thuy"


def test_json_ld_khong_dong_som_the_script():
    """Tên/bio do freelancer nhập; trong `<script>` thì HTML-escape không cứu được."""
    html = _render(full_name="</script><script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in html
    assert html.count("</script>") == 1


def test_thuoc_tinh_meta_duoc_thoat():
    html = _render(description='" onload="alert(1)')
    assert 'onload="alert(1)"' not in html
    assert "&#34;" in html or "&quot;" in html


def test_trang_404_co_noindex():
    assert 'name="robots" content="noindex' in seo_renderer.render_not_found_page()


def test_sitemap_co_home_va_tung_ho_so():
    xml = seo_renderer.render_sitemap(
        home_url="https://solodesk.space/home",
        entries=[
            seo_renderer.SitemapEntry(loc="https://solodesk.space/thu-thuy", lastmod="2026-08-21")
        ],
    )
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' in xml
    assert "<loc>https://solodesk.space/home</loc>" in xml
    assert "<loc>https://solodesk.space/thu-thuy</loc>" in xml
    assert "<lastmod>2026-08-21</lastmod>" in xml


def test_sitemap_thoat_ky_tu_xml():
    xml = seo_renderer.render_sitemap(home_url="https://solodesk.space/home?a=1&b=2", entries=[])
    assert "&amp;b=2" in xml


def test_lastmod_dung_dinh_dang_ngay():
    assert seo_renderer.format_lastmod(datetime(2026, 8, 21, 13, 5, tzinfo=UTC)) == "2026-08-21"
