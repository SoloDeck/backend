"""Async S3-compatible object storage client.

Thin wrapper around boto3 executed in a thread pool so it does not block
the event loop (mirrors ``src/shared/email/smtp.py``). Works against AWS S3
or any S3-compatible provider (MinIO, Cloudflare R2, DigitalOcean Spaces...)
via ``settings.storage_endpoint``. The target bucket is expected to be
configured for public read at the bucket-policy level — object ACLs are
not set here since not all S3-compatible providers support them.
"""

import asyncio
from dataclasses import dataclass
from functools import lru_cache

import boto3
import structlog

from src.config.settings import settings

logger = structlog.get_logger(__name__)


@lru_cache(maxsize=1)
def _get_client():  # type: ignore[no-untyped-def]
    kwargs: dict[str, str] = {"region_name": settings.storage_region}
    if settings.storage_endpoint:
        kwargs["endpoint_url"] = settings.storage_endpoint
    if settings.storage_access_key and settings.storage_secret_key:
        kwargs["aws_access_key_id"] = settings.storage_access_key
        kwargs["aws_secret_access_key"] = settings.storage_secret_key
    return boto3.client("s3", **kwargs)


def _public_url(key: str) -> str:
    if settings.storage_endpoint:
        return f"{settings.storage_endpoint.rstrip('/')}/{settings.storage_bucket}/{key}"
    return f"https://{settings.storage_bucket}.s3.{settings.storage_region}.amazonaws.com/{key}"


def _upload_sync(*, key: str, content: bytes, content_type: str) -> str:
    _get_client().put_object(
        Bucket=settings.storage_bucket,
        Key=key,
        Body=content,
        ContentType=content_type,
    )
    return _public_url(key)


@dataclass
class S3StorageClient:
    """Uploads objects to S3-compatible storage."""

    async def upload(self, *, key: str, content: bytes, content_type: str) -> str:
        try:
            url = await asyncio.to_thread(
                _upload_sync, key=key, content=content, content_type=content_type
            )
            logger.info("storage.upload_succeeded", key=key)
            return url
        except Exception as exc:
            logger.error("storage.upload_failed", key=key, error=str(exc))
            raise
