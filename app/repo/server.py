import json
import logging
from datetime import datetime
from typing import Optional, Dict

from .base import BaseRepository

CACHE_TTL_SERVERS = 120

LOG = logging.getLogger(__name__)

class ServerRepository(BaseRepository):
    
    async def get_best(self) -> Optional[Dict]:
        redis = await self._get_redis()
        pool = await self._get_pool()
        
        key = "servers:best"
        cached = await redis.get(key)
        if cached:
            return json.loads(cached)
        
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT * FROM servers 
                   WHERE load_avg < 75 
                   ORDER BY load_avg ASC, updated_at DESC 
                   LIMIT 1"""
            )
            if not row:
                row = await conn.fetchrow(
                    "SELECT * FROM servers ORDER BY load_avg ASC, updated_at DESC LIMIT 1"
                )
            
            if not row:
                LOG.warning("No servers available in database")
                return None
            
            server = dict(row)
            if 'updated_at' in server and isinstance(server['updated_at'], datetime):
                server['updated_at'] = server['updated_at'].isoformat()
        
        await redis.setex(key, CACHE_TTL_SERVERS, json.dumps(server))
        return server

    async def increment_users(self, server_id: str):
        redis = await self._get_redis()
        pool = await self._get_pool()
        
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE servers SET users_count = users_count + 1 WHERE id=$1",
                server_id
            )
        await redis.delete("servers:best")

    async def decrement_users(self, server_id: str):
        redis = await self._get_redis()
        pool = await self._get_pool()
        
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE servers SET users_count = users_count - 1 WHERE id=$1 AND users_count > 0",
                server_id
            )
        await redis.delete("servers:best")