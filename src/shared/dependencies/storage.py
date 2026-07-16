from typing import Annotated

from fastapi import Depends

from src.integrations.storage.client import StorageClient
from src.integrations.storage.s3_client import S3StorageClient


def get_storage_client() -> StorageClient:
    return S3StorageClient()


StorageDep = Annotated[StorageClient, Depends(get_storage_client)]
