"""Storage client interface.

Business modules depend on this Protocol, never on a concrete provider
implementation (e.g. ``S3StorageClient``), so the provider can be swapped
or faked in tests without touching module code.
"""

from typing import Protocol


class StorageClient(Protocol):
    async def upload(self, *, key: str, content: bytes, content_type: str) -> str:
        """Upload an object and return its publicly accessible URL."""
        ...
