import json
import logging
import re
import time
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, List
from urllib.parse import urlparse, urlunparse

from app.client import (
    marzban_add_user,
    marzban_remove_user,
    marzban_renew_user,
    marzban_get_user,
    marzban_modify_user,
)
from .base import BaseRepository

from config import REFERRAL_BONUS, REDIS_TTL

LOG = logging.getLogger(__name__)

CACHE_TTL_CONFIGS = REDIS_TTL
CACHE_TTL_SUB_END = REDIS_TTL
CACHE_TTL_LANG = 3600
CACHE_TTL_BALANCE = REDIS_TTL



class UserRepository(BaseRepository):
    
    @staticmethod
    def _validate_username(username: str) -> bool:
        return bool(re.match(r'^orbit_\d+$', username))

    async def get_balance(self, tg_id: int) -> Decimal:
        redis = await self._get_redis()
        pool = await self._get_pool()
        
        key = f"user:{tg_id}:balance"
        cached = await redis.get(key)
        if cached is not None:
            return Decimal(cached)

        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT balance FROM users WHERE tg_id=$1", tg_id)
            balance = row["balance"] if row else Decimal("0.0")

        await redis.setex(key, CACHE_TTL_BALANCE, str(balance))
        return balance

    async def change_balance(self, tg_id: int, amount: Decimal) -> Decimal:
        redis = await self._get_redis()
        pool = await self._get_pool()
        
        async with pool.acquire() as conn:
            new_balance = await conn.fetchval(
                "UPDATE users SET balance = balance + $1 WHERE tg_id = $2 RETURNING balance",
                amount, tg_id
            )
        
        if new_balance is not None:
            await redis.setex(f"user:{tg_id}:balance", CACHE_TTL_BALANCE, str(new_balance))
            return new_balance
        return Decimal("0.0")

    async def add_if_not_exists(
        self, 
        tg_id: int, 
        username: str, 
        referrer_id: Optional[int] = None, 
        user_ip: Optional[str] = None
    ) -> bool:
        redis = await self._get_redis()
        pool = await self._get_pool()
        
        now = datetime.utcnow()
        async with pool.acquire() as conn:
            async with conn.transaction():
                created_tg_id = await conn.fetchval(
                    """
                    INSERT INTO users (tg_id, username, user_ip, balance, plan, created_at, configs, lang, referrer_id, first_buy)
                    VALUES ($1, $2, $3, 0, NULL, $4, 0, 'ru', $5, TRUE)
                    ON CONFLICT (tg_id) DO NOTHING
                    RETURNING tg_id
                    """,
                    tg_id, username, user_ip, now, referrer_id
                )

                if created_tg_id and referrer_id:
                    await conn.execute(
                        "UPDATE users SET balance = balance + $1 WHERE tg_id=$2",
                        Decimal(str(REFERRAL_BONUS)), tg_id
                    )
                    await redis.delete(f"user:{referrer_id}:balance")

        return bool(created_tg_id)

    async def get_configs(self, tg_id: int) -> List[Dict]:
        redis = await self._get_redis()
        pool = await self._get_pool()
        
        key = f"user:{tg_id}:configs"
        cached = await redis.get(key)
        if cached:
            return json.loads(cached)
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, name, vless_link, server_id, username FROM configs WHERE tg_id=$1 ORDER BY id",
                tg_id
            )
            configs = [dict(r) for r in rows]
        
        await redis.setex(key, CACHE_TTL_CONFIGS, json.dumps(configs))
        return configs

    async def add_config(self, tg_id: int, vless_link: str, server_id: str, username: str) -> Dict:
        redis = await self._get_redis()
        pool = await self._get_pool()
        
        async with pool.acquire() as conn:
            async with conn.transaction():
                count = await conn.fetchval("SELECT COUNT(*) FROM configs WHERE tg_id=$1", tg_id)
                new_name = f"Configuration {count + 1}"
                row = await conn.fetchrow(
                    """INSERT INTO configs (tg_id, name, vless_link, server_id, username) 
                       VALUES ($1, $2, $3, $4, $5) 
                       RETURNING id, name, vless_link, server_id, username""",
                    tg_id, new_name, vless_link, server_id, username
                )
                await conn.execute("UPDATE users SET configs = configs + 1 WHERE tg_id=$1", tg_id)
        
        await redis.delete(f"user:{tg_id}:configs")
        return dict(row)

    async def delete_config(self, cfg_id: int, tg_id: int):
        redis = await self._get_redis()
        pool = await self._get_pool()
        
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT server_id, username FROM configs WHERE id=$1 AND tg_id=$2",
                    cfg_id, tg_id
                )
                if not row:
                    return
                
                server_id = row['server_id']
                username = row['username']
                
                await conn.execute("DELETE FROM configs WHERE id=$1 AND tg_id=$2", cfg_id, tg_id)
                await conn.execute(
                    "UPDATE users SET configs = configs - 1 WHERE tg_id=$1 AND configs > 0",
                    tg_id
                )
                await conn.execute(
                    "UPDATE servers SET users_count = users_count - 1 WHERE id=$1 AND users_count > 0",
                    server_id
                )
        
        try:
            await marzban_modify_user(username, expire=int(time.time() - 86400))
        except Exception as e:
            LOG.exception("marzban modify on delete failed: %s", e)
        
        await redis.delete(f"user:{tg_id}:configs")
        await redis.delete("servers:best")

    async def get_lang(self, tg_id: int) -> str:
        redis = await self._get_redis()
        pool = await self._get_pool()
        
        key = f"user:{tg_id}:lang"
        lang = await redis.get(key)
        if lang:
            return lang
        
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT lang FROM users WHERE tg_id=$1", tg_id)
            lang = row["lang"] if row else "ru"
        
        await redis.setex(key, CACHE_TTL_LANG, lang)
        return lang

    async def set_lang(self, tg_id: int, lang: str):
        redis = await self._get_redis()
        pool = await self._get_pool()
        
        await redis.setex(f"user:{tg_id}:lang", CACHE_TTL_LANG, lang)
        async with pool.acquire() as conn:
            await conn.execute("UPDATE users SET lang=$1 WHERE tg_id=$2", lang, tg_id)

    async def get_subscription_end(self, tg_id: int) -> Optional[float]:
        redis = await self._get_redis()
        pool = await self._get_pool()
        
        key = f"user:{tg_id}:sub_end"
        cached = await redis.get(key)
        if cached:
            return float(cached) if cached != 'None' else None
        
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT subscription_end FROM users WHERE tg_id=$1", tg_id)
            sub_end = row['subscription_end'].timestamp() if row and row['subscription_end'] else None
        
        await redis.setex(key, CACHE_TTL_SUB_END, str(sub_end) if sub_end else 'None')
        return sub_end

    async def set_subscription_end(self, tg_id: int, timestamp: float):
        redis = await self._get_redis()
        pool = await self._get_pool()
        
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET subscription_end=$1 WHERE tg_id=$2",
                datetime.fromtimestamp(timestamp), tg_id
            )
        await redis.setex(f"user:{tg_id}:sub_end", CACHE_TTL_SUB_END, str(timestamp))

    async def has_active_subscription(self, tg_id: int) -> bool:
        sub_end = await self.get_subscription_end(tg_id)
        if not sub_end:
            return False
        return time.time() < sub_end

    async def buy_subscription(self, tg_id: int, days: int, price: float) -> bool:
        redis = await self._get_redis()
        pool = await self._get_pool()
        
        price_decimal = Decimal(str(price))
        
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """SELECT balance, subscription_end, first_buy, referrer_id 
                       FROM users WHERE tg_id=$1 FOR UPDATE""",
                    tg_id
                )
                if not row:
                    LOG.warning(f"User {tg_id} not found during subscription purchase")
                    return False

                balance = row['balance']
                if balance < price_decimal:
                    LOG.info(f"User {tg_id} has insufficient balance: {balance} < {price_decimal}")
                    return False

                new_balance = balance - price_decimal
                await conn.execute("UPDATE users SET balance=$1 WHERE tg_id=$2", new_balance, tg_id)

                current_sub_ts = row['subscription_end'].timestamp() if row['subscription_end'] else None
                now = time.time()
                new_end = max(current_sub_ts or now, now) + (days * 86400)
                await conn.execute(
                    "UPDATE users SET subscription_end=$1 WHERE tg_id=$2",
                    datetime.fromtimestamp(new_end), tg_id
                )

                is_first_buy = row['first_buy']
                referrer_id = row['referrer_id']

                if is_first_buy:
                    await conn.execute("UPDATE users SET first_buy=FALSE WHERE tg_id=$1", tg_id)
                    if referrer_id:
                        referral_bonus = Decimal(str(REFERRAL_BONUS))
                        await conn.execute(
                            "UPDATE users SET balance = balance + $1 WHERE tg_id=$2",
                            referral_bonus, referrer_id
                        )
                        await redis.delete(f"user:{referrer_id}:balance")
                        LOG.info(f"Referral bonus {REFERRAL_BONUS} credited to {referrer_id} from {tg_id}")

        await redis.setex(f"user:{tg_id}:sub_end", CACHE_TTL_SUB_END, str(new_end))
        await redis.setex(f"user:{tg_id}:balance", CACHE_TTL_BALANCE, str(new_balance))
        
        LOG.info(f"User {tg_id} purchased {days} days for {price} RUB. New balance: {new_balance}")
        return True

    async def create_and_add_config(self, tg_id: int, server_id: str) -> Dict:
        redis = await self._get_redis()
        pool = await self._get_pool()
        
        username = f'orbit_{tg_id}'
        if not self._validate_username(username):
            raise ValueError("Invalid username format")
        
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT subscription_end FROM users WHERE tg_id=$1 FOR UPDATE",
                    tg_id
                )
                if not row or not row['subscription_end']:
                    raise ValueError("No active subscription")
                
                sub_end = row['subscription_end'].timestamp()
                if time.time() >= sub_end:
                    raise ValueError("Subscription expired")
                
                count = await conn.fetchval("SELECT COUNT(*) FROM configs WHERE tg_id=$1", tg_id)
                if count >= 1:
                    raise ValueError("Max configs reached (limit: 1)")
                
                days_remaining = max(1, int((sub_end - time.time()) / 86400) + 1)
        
        try:
            new_user = await marzban_add_user(username=username, days=days_remaining)
            vless_link = new_user.links[0]
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str or "409" in error_str:
                LOG.warning(f"User {username} already exists in Marzban, fetching existing")
                user = await marzban_get_user(username)
                expire_timestamp = int(sub_end)
                await marzban_modify_user(username, expire=expire_timestamp)
                vless_link = user.links[0] if user.links else None
                if not vless_link:
                    raise ValueError("No VLESS link found for existing user")
            else:
                LOG.exception(f"Marzban add_user failed for {username}: {e}")
                raise
        
        parsed = urlparse(vless_link)
        vless_link = urlunparse(parsed._replace(fragment="OrbitVPN"))
        
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT subscription_end FROM users WHERE tg_id=$1 FOR UPDATE",
                    tg_id
                )
                if not row or not row['subscription_end'] or time.time() >= row['subscription_end'].timestamp():
                    try:
                        await marzban_modify_user(username, expire=int(time.time() - 86400))
                    except Exception as e:
                        LOG.error(f"Failed to expire Marzban user {username}: {e}")
                    raise ValueError("Subscription expired during config creation")
                
                count = await conn.fetchval("SELECT COUNT(*) FROM configs WHERE tg_id=$1", tg_id)
                if count >= 1:
                    raise ValueError("Max configs reached during creation")
                
                new_name = f"Configuration {count + 1}"
                config_row = await conn.fetchrow(
                    """INSERT INTO configs (tg_id, name, vless_link, server_id, username) 
                       VALUES ($1, $2, $3, $4, $5) 
                       RETURNING id, name, vless_link, server_id, username""",
                    tg_id, new_name, vless_link, server_id, username
                )
                await conn.execute("UPDATE users SET configs = configs + 1 WHERE tg_id=$1", tg_id)
                await conn.execute("UPDATE servers SET users_count = users_count + 1 WHERE id=$1", server_id)
        
        await redis.delete(f"user:{tg_id}:configs")
        await redis.delete("servers:best")
        
        LOG.info(f"Config created for user {tg_id} on server {server_id}")
        return dict(config_row)