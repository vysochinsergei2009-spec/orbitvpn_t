import os
import redis.asyncio as redis

redis_client: redis.Redis = None

async def init_cache():
    global redis_client
    if redis_client is None:
        try:
            url = os.getenv("REDIS_URL", "redis://localhost")
            redis_client = await redis.from_url(
                url,
                encoding="utf-8",
                decode_responses=True
            )
            await redis_client.ping()
            print("Redis connected")
        except Exception as e:
            print(f"Redis init error: {e}")
            raise

async def get_redis() -> redis.Redis:
    if redis_client is None:
        raise RuntimeError("Redis not initialized. Call init_cache() first.")
    return redis_client

async def close_cache():
    global redis_client
    if redis_client is not None:
        await redis_client.close()
        print("Redis closed")
        redis_client = None
