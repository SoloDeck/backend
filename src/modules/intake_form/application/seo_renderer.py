"""Trang HTML/XML dành cho bot tìm kiếm.

Web của SoloDesk là SPA render phía trình duyệt, nên `/{slug}` gửi tới Googlebot chỉ là
một cái vỏ rỗng. Các trang ở đây là bản render sẵn của cùng hồ sơ đó, để reverse proxy
đưa cho bot; người dùng thật vẫn nhận SPA như cũ.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_DESCRIPTION_MAX_CHARS = 160

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent.parent / "templates"),
    autoescape=True,
)


def truncate_description(text: str | None, *, fallback: str) -> str:
    """Gộp khoảng trắng rồi cắt ở ranh giới từ — meta description dài quá bị Google cắt cụt."""
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return fallback
    if len(cleaned) <= _DESCRIPTION_MAX_CHARS:
        return cleaned
    head = cleaned[: _DESCRIPTION_MAX_CHARS - 1]
    cut = head.rsplit(" ", 1)[0] if " " in head else head
    return f"{cut}…"


def _json_ld(payload: dict) -> str:
    """Serialize JSON-LD an toàn để nhúng thẳng vào `<script>`.

    Trong `<script>` thì HTML-escape của Jinja KHÔNG có tác dụng (trình duyệt không giải
    entity ở đó) mà lại làm hỏng JSON, nên template dùng `| safe`. Bù lại, ba ký tự có thể
    đóng sớm thẻ script được thoát về dạng \\uXXXX ngay tại đây — dữ liệu do freelancer tự
    nhập nên đây là bề mặt XSS thật.
    """
    raw = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    return raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


@dataclass(frozen=True)
class SitemapEntry:
    loc: str
    lastmod: str


def render_profile_page(
    *,
    full_name: str,
    professional_title: str | None,
    description: str,
    image_url: str,
    canonical_url: str,
    skills: list[str],
) -> str:
    json_ld = _json_ld(
        {
            "@context": "https://schema.org",
            "@type": "ProfilePage",
            "url": canonical_url,
            "mainEntity": {
                "@type": "Person",
                "name": full_name,
                "url": canonical_url,
                "image": image_url,
                "description": description,
                **({"jobTitle": professional_title} if professional_title else {}),
                **({"knowsAbout": skills} if skills else {}),
            },
        }
    )
    return _env.get_template("profile_seo.html").render(
        title=f"{full_name} — SoloDesk",
        full_name=full_name,
        professional_title=professional_title,
        description=description,
        image=image_url,
        url=canonical_url,
        skills=skills,
        json_ld=json_ld,
    )


def render_not_found_page() -> str:
    return _env.get_template("profile_seo_not_found.html").render()


def render_sitemap(*, home_url: str, entries: list[SitemapEntry]) -> str:
    return _env.get_template("sitemap.xml").render(home_url=home_url, entries=entries)


def format_lastmod(value: datetime) -> str:
    return value.date().isoformat()
