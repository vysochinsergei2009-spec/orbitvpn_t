from .db import get_session, AsyncSession
import redis.asyncio as redis

class BaseRepository:
    def __init__(self, session: AsyncSession, redis_client: redis.Redis = None):
        self.session = session
        self.redis = redis_client

    async def get_redis(self) -> redis.Redis:
        if self.redis is None:
            raise RuntimeError("Redis client not provided")
        return self.redis