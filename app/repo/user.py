import json
import re
import time
from decimal import Decimal
from datetime import datetime
from typing import Optional, List, Dict
from urllib.parse import urlparse, urlunparse

from sqlalchemy import select, update, func

from .models import User, Config, Server
from .db import get_session
from .marzban_client import MarzbanClient
from app.utils.logging import get_logger
from .base import BaseRepository
from config import REFERRAL_BONUS, REDIS_TTL

LOG = get_logger(__name__)

CACHE_TTL_BALANCE = 60
CACHE_TTL_CONFIGS = 600
CACHE_TTL_SUB_END = 3600
CACHE_TTL_LANG = 86400
CACHE_TTL_NOTIFICATIONS = 3600

class UserRepository(BaseRepository):

    @staticmethod
    def _validate_username(username: str) -> bool:
        return bool(re.match(r'^orbit_\d+$', username))

    # ----------------------------
    # Balance
    # ----------------------------
    async def get_balance(self, tg_id: int) -> Decimal:
        """
        Get user balance with Redis caching and automatic fallback to database.

        CRITICAL: Redis failures are handled gracefully - if Redis is unavailable,
        the method falls back to database without failing.
        """
        redis = await self.get_redis()

        # Try to get from cache, but don't fail if Redis is down
        try:
            cached = await redis.get(f"user:{tg_id}:balance")
            if cached:
                return Decimal(cached)
        except Exception as e:
            LOG.warning(f"Redis error reading balance for user {tg_id}: {e}")
            # Continue to database fallback

        # Fallback to database
        result = await self.session.execute(select(User.balance).filter_by(tg_id=tg_id))
        balance = result.scalar() or Decimal("0.0")

        # Try to cache the result, but don't fail if Redis is down
        try:
            await redis.setex(f"user:{tg_id}:balance", CACHE_TTL_BALANCE, str(balance))
        except Exception as e:
            LOG.warning(f"Redis error caching balance for user {tg_id}: {e}")
            # Continue anyway - database read succeeded

        return balance

    async def change_balance(self, tg_id: int, amount: Decimal) -> Decimal:
        """
        Change user balance atomically with SELECT FOR UPDATE lock.

        CRITICAL: This method now uses row-level locking to prevent lost updates
        from concurrent balance modifications (race conditions).

        Returns:
            New balance after change

        Raises:
            ValueError: If user not found or insufficient balance
        """
        redis = await self.get_redis()

        # CRITICAL FIX: Lock user row BEFORE reading balance
        # This prevents race conditions where two concurrent updates both read
        # the same balance value and one update gets lost
        result = await self.session.execute(
            select(User)
            .where(User.tg_id == tg_id)
            .with_for_update()  # Acquire exclusive lock on row
        )
        user = result.scalar_one_or_none()

        if not user:
            raise ValueError(f"User {tg_id} not found")

        old_balance = user.balance
        new_balance = old_balance + amount

        # Prevent negative balance
        if new_balance < 0:
            raise ValueError(f"Insufficient balance: {old_balance} + {amount} = {new_balance}")

        # Update locked row
        user.balance = new_balance
        await self.session.commit()

        LOG.info(f"Balance changed for user {tg_id}: {old_balance} → {new_balance} ({amount:+.2f})")

        # Invalidate cache after successful commit (tolerate Redis failures)
        try:
            await redis.delete(f"user:{tg_id}:balance")
        except Exception as e:
            LOG.warning(f"Redis error invalidating balance cache for user {tg_id}: {e}")
            # Don't fail the transaction - balance was successfully updated in database

        return new_balance

    # ----------------------------
    # Add user if not exists
    # ----------------------------
    async def add_if_not_exists(
        self,
        tg_id: int,
        username: str,
        referrer_id: Optional[int] = None
    ) -> bool:
        redis = await self.get_redis()
        now = datetime.utcnow()

        user = await self.session.get(User, tg_id)
        if user:
            return False

        new_user = User(
            tg_id=tg_id,
            username=username,
            balance=0,
            configs=0,
            lang='ru',
            referrer_id=referrer_id,
            first_buy=True,
            notifications=True,
            created_at=now
        )
        self.session.add(new_user)

        if referrer_id:
            await self.session.execute(
                update(User)
                .where(User.tg_id == referrer_id)
                .values(balance=User.balance + REFERRAL_BONUS)
            )
            await redis.delete(f"user:{referrer_id}:balance")

        await self.session.commit()
        return True

    # ----------------------------
    # Configs
    # ----------------------------
    async def get_configs(self, tg_id: int) -> List[Dict]:
        redis = await self.get_redis()
        key = f"user:{tg_id}:configs"
        cached = await redis.get(key)
        if cached:
            return json.loads(cached)

        result = await self.session.execute(
            select(Config).filter_by(tg_id=tg_id, deleted=False).order_by(Config.id)
        )
        configs = [dict(
            id=c.id,
            name=c.name,
            vless_link=c.vless_link,
            server_id=c.server_id,
            username=c.username
        ) for c in result.scalars().all()]

        await redis.setex(key, CACHE_TTL_CONFIGS, json.dumps(configs))
        return configs

    async def add_config(self, tg_id: int, vless_link: str, server_id: str, username: str) -> Dict:
        redis = await self.get_redis()

        result = await self.session.execute(
            select(func.count(Config.id)).filter_by(tg_id=tg_id, deleted=False)
        )
        count = result.scalar() or 0
        new_name = f"Configuration {count + 1}"

        cfg = Config(
            tg_id=tg_id,
            name=new_name,
            vless_link=vless_link,
            server_id=server_id,
            username=username,
            deleted=False
        )
        self.session.add(cfg)

        await self.session.execute(
            update(User)
            .where(User.tg_id == tg_id)
            .values(configs=User.configs + 1)
        )

        await self.session.commit()

        await redis.delete(f"user:{tg_id}:configs")
        return {
            "id": cfg.id,
            "name": cfg.name,
            "vless_link": cfg.vless_link,
            "server_id": cfg.server_id,
            "username": cfg.username
        }

    # ----------------------------
    # Marzban safe wrappers
    # ----------------------------
    async def _safe_remove_marzban_user(self, username: str):
        marzban_client = MarzbanClient()
        try:
            await marzban_client.remove_user(username)
            LOG.info("Removed marzban user %s", username)
        except Exception as e:
            LOG.warning("Failed to remove marzban user %s: %s", username, e)
            try:
                await marzban_client.modify_user(username, expire=int(time.time() - 86400))
                LOG.info("Expired marzban user %s as fallback", username)
            except Exception as ex:
                LOG.error("Failed to expire marzban user %s during fallback: %s", username, ex)

    async def _safe_modify_marzban_user(self, username: str, expire_ts: int):
        marzban_client = MarzbanClient()
        try:
            await marzban_client.modify_user(username, expire=expire_ts)
            LOG.info("Modified marzban user %s expire=%s", username, expire_ts)
        except Exception as e:
            LOG.error("Failed to modify marzban user %s expire=%s: %s", username, expire_ts, e)

    # ----------------------------
    # Delete config (clean delete)
    # ----------------------------
    async def delete_config(self, cfg_id: int, tg_id: int):
        redis = await self.get_redis()
        username = None

        cfg = await self.session.get(Config, cfg_id)
        if not cfg or cfg.tg_id != tg_id or cfg.deleted:
            LOG.debug("delete_config: config not found or already deleted id=%s tg=%s", cfg_id, tg_id)
            return

        username = cfg.username

        cfg.deleted = True
        await self.session.execute(
            update(User)
            .where(User.tg_id == tg_id)
            .values(configs=func.greatest(User.configs - 1, 0))
        )
        await self.session.commit()

        if username:
            await self._safe_remove_marzban_user(username)

        await redis.delete(f"user:{tg_id}:configs")

    # ----------------------------
    # Language
    # ----------------------------
    async def get_lang(self, tg_id: int) -> str:
        redis = await self.get_redis()
        key = f"user:{tg_id}:lang"
        cached = await redis.get(key)
        if cached:
            return cached

        user = await self.session.get(User, tg_id)
        lang = user.lang if user else "ru"

        await redis.setex(key, CACHE_TTL_LANG, lang)
        return lang

    async def set_lang(self, tg_id: int, lang: str):
        redis = await self.get_redis()
        await redis.setex(f"user:{tg_id}:lang", CACHE_TTL_LANG, lang)

        await self.session.execute(update(User).where(User.tg_id == tg_id).values(lang=lang))
        await self.session.commit()

    # ----------------------------
    # Notifications
    # ----------------------------
    async def get_notifications(self, tg_id: int) -> bool:
        redis = await self.get_redis()
        key = f"user:{tg_id}:notifications"

        try:
            cached = await redis.get(key)
            if cached is not None:
                return cached == "1"
        except Exception as e:
            LOG.warning(f"Redis error reading notifications for user {tg_id}: {e}")

        user = await self.session.get(User, tg_id)
        notifications = user.notifications if user and user.notifications is not None else True

        try:
            await redis.setex(key, CACHE_TTL_NOTIFICATIONS, "1" if notifications else "0")
        except Exception as e:
            LOG.warning(f"Redis error caching notifications for user {tg_id}: {e}")

        return notifications

    async def toggle_notifications(self, tg_id: int) -> bool:
        redis = await self.get_redis()

        user = await self.session.get(User, tg_id)
        if not user:
            LOG.warning(f"User {tg_id} not found during toggle_notifications")
            return True

        new_state = not (user.notifications if user.notifications is not None else True)

        await self.session.execute(
            update(User).where(User.tg_id == tg_id).values(notifications=new_state)
        )
        await self.session.commit()

        try:
            await redis.setex(f"user:{tg_id}:notifications", CACHE_TTL_NOTIFICATIONS, "1" if new_state else "0")
        except Exception as e:
            LOG.warning(f"Redis error updating notifications cache for user {tg_id}: {e}")

        LOG.info(f"Notifications toggled for user {tg_id}: {new_state}")
        return new_state

    # ----------------------------
    # Subscription helpers
    # ----------------------------
    async def get_subscription_end(self, tg_id: int) -> Optional[float]:
        redis = await self.get_redis()
        key = f"user:{tg_id}:sub_end"
        cached = await redis.get(key)
        if cached:
            return float(cached) if cached != 'None' else None

        result = await self.session.execute(select(User.subscription_end).where(User.tg_id == tg_id))
        sub_end_dt = result.scalar()
        sub_end = sub_end_dt.timestamp() if sub_end_dt else None

        await redis.setex(key, CACHE_TTL_SUB_END, str(sub_end) if sub_end else 'None')
        return sub_end

    async def set_subscription_end(self, tg_id: int, timestamp: float):
        redis = await self.get_redis()
        expire_dt = datetime.fromtimestamp(timestamp)

        await self.session.execute(
            update(User).where(User.tg_id == tg_id).values(subscription_end=expire_dt)
        )
        result = await self.session.execute(select(Config.username).where(Config.tg_id == tg_id, Config.deleted == False))
        usernames = [r[0] for r in result.all()]
        await self.session.commit()

        await redis.setex(f"user:{tg_id}:sub_end", CACHE_TTL_SUB_END, str(timestamp))

        if usernames:
            import asyncio
            await asyncio.gather(*[
                self._safe_modify_marzban_user(username, int(timestamp))
                for username in usernames
            ], return_exceptions=True)

    async def has_active_subscription(self, tg_id: int) -> bool:
        sub_end = await self.get_subscription_end(tg_id)
        if not sub_end:
            return False
        return time.time() < sub_end

    async def buy_subscription(self, tg_id: int, days: int, price: float) -> bool:
        redis = await self.get_redis()
        price_decimal = Decimal(str(price))
        now_ts = time.time()

        result = await self.session.execute(
            select(User).where(User.tg_id == tg_id).with_for_update()
        )
        user = result.scalar_one_or_none()
        if not user:
            LOG.warning(f"User {tg_id} not found during subscription purchase")
            return False

        if user.balance < price_decimal:
            LOG.info(f"User {tg_id} has insufficient balance: {user.balance} < {price_decimal}")
            return False

        new_balance = user.balance - price_decimal
        user.balance = new_balance

        current_sub_ts = user.subscription_end.timestamp() if user.subscription_end else now_ts
        new_end_ts = max(current_sub_ts, now_ts) + days * 86400
        user.subscription_end = datetime.fromtimestamp(new_end_ts)

        if user.first_buy:
            user.first_buy = False
            if user.referrer_id:
                ref_result = await self.session.execute(
                    select(User).where(User.tg_id == user.referrer_id)
                )
                ref_user = ref_result.scalar_one_or_none()
                if ref_user:
                    ref_user.balance += Decimal(str(REFERRAL_BONUS))
                    await redis.delete(f"user:{user.referrer_id}:balance")
                    LOG.info(f"Referral bonus {REFERRAL_BONUS} credited to {user.referrer_id} from {tg_id}")

        result = await self.session.execute(select(Config.username).where(Config.tg_id == tg_id, Config.deleted == False))
        usernames = [r[0] for r in result.all()]

        await self.session.commit()

        await redis.setex(f"user:{tg_id}:sub_end", CACHE_TTL_SUB_END, str(new_end_ts))
        await redis.setex(f"user:{tg_id}:balance", CACHE_TTL_BALANCE, str(new_balance))

        if usernames:
            import asyncio
            await asyncio.gather(*[
                self._safe_modify_marzban_user(username, int(new_end_ts))
                for username in usernames
            ], return_exceptions=True)

        LOG.info(f"User {tg_id} purchased {days} days for {price} RUB. New balance: {new_balance}")
        return True

    async def create_and_add_config(
        self,
        tg_id: int,
        manual_instance_id: Optional[str] = None
    ) -> Dict:

        redis = await self.get_redis()
        username = f'orbit_{tg_id}'

        if not self._validate_username(username):
            raise ValueError("Invalid username format")

        async with get_session() as session:
            result = await session.execute(
                select(User).where(User.tg_id == tg_id).with_for_update()
            )
            user = result.scalar_one_or_none()
            if not user or not user.subscription_end or time.time() >= user.subscription_end.timestamp():
                raise ValueError("No active subscription or subscription expired")

            result = await session.execute(
                select(func.count(Config.id)).where(
                    Config.tg_id == tg_id,
                    Config.deleted == False
                )
            )
            count = result.scalar()
            if count >= 1:
                raise ValueError("Max configs reached (limit: 1)")

            days_remaining = max(1, int((user.subscription_end.timestamp() - time.time()) / 86400) + 1)

        marzban_client = MarzbanClient()

        try:
            new_user = await marzban_client.add_user(
                username=username,
                days=days_remaining,
                manual_instance_id=manual_instance_id
            )
            if not new_user.links:
                raise ValueError("No VLESS link returned from Marzban")
            vless_link = new_user.links[0]

            instance, _, _ = await marzban_client.get_best_instance_and_node(manual_instance_id)
            instance_id = instance.id

        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str or "409" in error_str:
                LOG.warning("Marzban user %s already exists; attempting remove+recreate", username)
                await marzban_client.remove_user(username)
                new_user = await marzban_client.add_user(
                    username=username,
                    days=days_remaining,
                    manual_instance_id=manual_instance_id
                )
                if not new_user.links:
                    raise ValueError("No VLESS link after recreate")
                vless_link = new_user.links[0]
                instance, _, _ = await marzban_client.get_best_instance_and_node(manual_instance_id)
                instance_id = instance.id
            else:
                LOG.error("Marzban add_user failed for %s: %s", username, e)
                raise

        parsed = urlparse(vless_link)
        vless_link = urlunparse(parsed._replace(fragment="OrbitVPN"))

        async with get_session() as session:
            result = await session.execute(
                select(User).where(User.tg_id == tg_id).with_for_update()
            )
            user = result.scalar_one_or_none()
            if not user or not user.subscription_end or time.time() >= user.subscription_end.timestamp():
                await marzban_client.remove_user(username, instance_id)
                raise ValueError("Subscription expired during config creation")

            result = await session.execute(
                select(func.count(Config.id)).where(Config.tg_id == tg_id, Config.deleted == False)
            )
            count = result.scalar()
            if count >= 1:
                await marzban_client.remove_user(username, instance_id)
                raise ValueError("Max configs reached during creation")

            new_name = f"Configuration {count + 1}"
            cfg = Config(
                tg_id=tg_id,
                name=new_name,
                vless_link=vless_link,
                server_id=instance_id,
                username=username,
                deleted=False
            )
            session.add(cfg)
            await session.execute(
                update(User).where(User.tg_id == tg_id).values(configs=User.configs + 1)
            )
            await session.commit()

        await redis.delete(f"user:{tg_id}:configs")

        LOG.info("Config created for user %s on Marzban instance %s", tg_id, instance_id)
        return {
            "id": cfg.id,
            "name": cfg.name,
            "vless_link": cfg.vless_link,
            "server_id": cfg.server_id,
            "username": cfg.username
        }

    async def get_all_users(self) -> List[User]:
        """Get all users for broadcast"""
        session = self.session
        result = await session.execute(select(User))
        return list(result.scalars().all())

    async def get_users_with_notifications(self) -> List[User]:
        """Get users with notifications enabled for targeted broadcast"""
        session = self.session
        result = await session.execute(
            select(User).where(User.notifications == True)
        )
        return list(result.scalars().all())