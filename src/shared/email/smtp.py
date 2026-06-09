"""Async SMTP email sender.

Thin wrapper around Python's ``smtplib`` executed in a thread pool so it
does not block the event loop.
"""

import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import partial

import structlog

from src.config.settings import settings

logger = structlog.get_logger(__name__)


def _send_sync(*, to: str, subject: str, html: str, plain: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = to

    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    smtp_cls = smtplib.SMTP_SSL if settings.smtp_tls else smtplib.SMTP
    with smtp_cls(settings.smtp_host, settings.smtp_port) as server:
        if settings.smtp_user and settings.smtp_password:
            server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.smtp_from_email, [to], msg.as_string())


async def send_email(*, to: str, subject: str, html: str, plain: str) -> None:
    """Send an email asynchronously (runs SMTP in a thread pool)."""
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(
            None,
            partial(_send_sync, to=to, subject=subject, html=html, plain=plain),
        )
        logger.info("email.sent", to=to, subject=subject)
    except Exception as exc:
        logger.error("email.send_failed", to=to, subject=subject, error=str(exc))
        raise
