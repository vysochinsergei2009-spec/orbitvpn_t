import asyncio
from app.utils.db import get_pg_pool
from app.utils.redis import get_redis


class BaseRepository:
    def __init__(self):
        self._pool_lock = asyncio.Lock()
        self._redis_lock = asyncio.Lock()
        self._pool = None
        self._redis = None

    async def _get_pool(self):
        if self._pool is None:
            async with self._pool_lock:
                if self._pool is None:
                    self._pool = await get_pg_pool()
        return self._pool

    async def _get_redis(self):
        if self._redis is None:
            async with self._redis_lock:
                if self._redis is None:
                    self._redis = await get_redis()
        return self._redis