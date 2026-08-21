"""Route hạ tầng cho SEO — phục vụ bot, không thuộc API JSON.

Mount ở GỐC (không có `/api/v1`) và `include_in_schema=False`: hai route này không nằm
trong `contracts/openapi.yaml`, và quan trọng hơn, `_relativize_paths` trong `main.py` bỏ
qua toàn bộ việc rút gọn tiền tố nếu thấy MỘT path không bắt đầu bằng `/api/v1` — để
chúng lọt vào schema là làm mọi endpoint khác ở `/docs` dài ra.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session
from src.modules.intake_form.application.service import IntakeFormService
from src.shared.exceptions.domain import NotFoundError

router = APIRouter(include_in_schema=False)

DBSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/internal/render/profile/{slug}", response_class=HTMLResponse)
async def render_profile(slug: str, db: DBSession) -> HTMLResponse:
    """Bản render sẵn của `/{slug}` để reverse proxy đưa cho crawler."""
    service = IntakeFormService(db=db)
    try:
        html = await service.render_profile_seo_page(slug)
    except NotFoundError:
        # Trang 404 tự dựng thay vì để handler chung trả JSON: crawler đang chờ HTML, và
        # thẻ `noindex` phải có mặt để đường dẫn chết không bị đưa vào chỉ mục.
        return HTMLResponse(content=service.render_profile_seo_not_found_page(), status_code=404)
    return HTMLResponse(content=html)


@router.get("/sitemap.xml")
async def sitemap(db: DBSession) -> Response:
    xml = await IntakeFormService(db=db).render_sitemap()
    return Response(content=xml, media_type="application/xml")
