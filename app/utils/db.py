import asyncpg
from config import DATABASE_USER, DATABASE_PASSWORD, DATABASE_NAME, DATABASE_HOST

pg_pool: asyncpg.Pool = None

async def init_db():
    global pg_pool
    if pg_pool is None:
        pg_pool = await asyncpg.create_pool(
            user=DATABASE_USER,
            password=DATABASE_PASSWORD,
            database=DATABASE_NAME,
            host=DATABASE_HOST,
            min_size=5,
            max_size=40,
            ssl=False
        )
        try:
            async with pg_pool.acquire() as conn:
                row = await conn.fetchval("SELECT NOW()")
                print("PostgreSQL connected")
                print("DB Time:", row)
        except Exception as e:
            print(f"DB init error: {e}")
            raise

async def get_pg_pool() -> asyncpg.Pool:
    if pg_pool is None:
        raise RuntimeError("PostgreSQL not initialized. Call init_db() first.")
    return pg_pool

async def close_db():
    global pg_pool
    if pg_pool is not None:
        await pg_pool.close()
        print("PostgreSQL closed")
        pg_pool = None