"""Làm nóng WeasyPrint lúc API khởi động.

Lần dựng PDF ĐẦU TIÊN sau khi khởi động mất ~4,5–9 giây (nạp Pango, fontconfig, dựng cache font),
các lần sau chỉ 0,3–1 giây. Bấm "Gửi cho khách" ngay sau khi deploy mà SMTP cũng chậm thì cộng lại
vượt mốc chờ của trình duyệt, người dùng thấy "thất bại" dù thư đã đi. Dựng thử một PDF cực nhỏ
ở nền ngay khi khởi động để cái giá đó trả trước, không phải trả trên lưng người dùng đầu tiên.
#Huynh
"""

import time

import structlog

log = structlog.get_logger()


def warm_up_pdf_engine() -> float | None:
    """Dựng thử một PDF nhỏ, trả số giây đã mất, hoặc `None` nếu không làm nóng được.

    HÀM ĐỒNG BỘ, tốn CPU: gọi qua `asyncio.to_thread`, đừng gọi thẳng trong event loop.

    Không bao giờ ném lỗi ra ngoài. Máy thiếu thư viện hệ thống (Pango/GTK — máy Windows chạy dev)
    thì `import weasyprint` ném `OSError`; đó là chuyện môi trường, không được làm hỏng việc khởi
    động. Dựng PDF thật ở đường gửi báo giá vẫn sẽ báo lỗi đúng chỗ nếu thật sự thiếu.
    """
    started = time.perf_counter()
    try:
        from weasyprint import HTML  # lazy: cần thư viện hệ thống

        HTML(string="<p>warm-up</p>").write_pdf()
    except Exception as exc:  # noqa: BLE001 — OSError/ImportError/lỗi font, tất cả đều bỏ qua
        log.warning("pdf.warmup_skipped", error_type=type(exc).__name__, error=str(exc)[:200])
        return None
    elapsed = time.perf_counter() - started
    log.info("pdf.warmup_done", seconds=round(elapsed, 2))
    return elapsed
