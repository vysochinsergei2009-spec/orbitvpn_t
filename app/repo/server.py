"""
DEPRECATED: This module is deprecated in favor of MarzbanClient.

The Server model and ServerRepository are kept for backward compatibility only.
New code should use app.repo.marzban_client.MarzbanClient instead, which provides:
- Multi-instance Marzban support
- Automatic node load balancing
- Better scalability

This will be removed in a future version.
"""

import json
from datetime import datetime
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update
from .models import Server
from .db import get_session
from app.utils.logging import get_logger
import redis.asyncio as redis  # Явный импорт redis

LOG = get_logger(__name__)
CACHE_TTL_SERVERS = 120

class ServerRepository:
    """
    DEPRECATED: Use MarzbanClient instead.
    This repository is kept for backward compatibility only.
    """
    def __init__(self, redis):
        self.redis = redis

    async def _server_to_dict(self, server: Server) -> dict:
        server_dict = {c.name: getattr(server, c.name) for c in Server.__table__.columns}
        for key, value in server_dict.items():
            if isinstance(value, Decimal):
                server_dict[key] = float(value)  # Decimal в float
            elif isinstance(value, datetime):
                server_dict[key] = value.isoformat()  # datetime в ISO строку
            elif value is None:
                server_dict[key] = None
        return server_dict

    async def get_best(self) -> dict | None:
        key = "servers:best"
        try:
            cached = await self.redis.get(key)
            if cached:
                return json.loads(cached)
        except redis.RedisError as e:
            LOG.error(f"Redis error in get_best: {e}")

        async with get_session() as session:
            stmt = select(Server).order_by(Server.load_avg.asc(), Server.updated_at.desc()).limit(1)
            result = await session.execute(stmt)
            server = result.scalar_one_or_none()

            if server is None:
                LOG.warning("No servers available")
                return None

            server_dict = await self._server_to_dict(server)
            try:
                await self.redis.setex(key, CACHE_TTL_SERVERS, json.dumps(server_dict))
            except redis.RedisError as e:
                LOG.error(f"Redis error in setex: {e}")
            return server_dict

    async def increment_users(self, server_id: str):  # Изменено на str
        async with get_session() as session:
            async with session.begin():
                stmt = (
                    update(Server)
                    .where(Server.id == server_id)
                    .values(users_count=Server.users_count + 1)
                )
                await session.execute(stmt)
            try:
                await self.redis.delete("servers:best")
            except redis.RedisError as e:
                LOG.error(f"Redis error in increment_users: {e}")

    async def decrement_users(self, server_id: str):
        async with get_session() as session:
            async with session.begin():
                stmt = (
                    update(Server)
                    .where(Server.id == server_id, Server.users_count > 0)
                    .values(users_count=Server.users_count - 1)
                )
                await session.execute(stmt)
            try:
                await self.redis.delete("servers:best")
            except redis.RedisError as e:
                LOG.error(f"Redis error in decrement_users: {e}")