from redis.asyncio import Redis, ConnectionPool
from src.config.settings import settings

_pool: ConnectionPool | None = None


def get_redis_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(
            str(settings.redis_url),
            decode_responses=True,
            max_connections=20,
        )
    return _pool


async def get_redis() -> Redis:  # type: ignore[type-arg]
    """FastAPI dependency — returns a Redis client from the shared pool."""
    return Redis(connection_pool=get_redis_pool())


async def close_redis_pool() -> None:
    global _pool
    if _pool:
        await _pool.disconnect()
        _pool = None
