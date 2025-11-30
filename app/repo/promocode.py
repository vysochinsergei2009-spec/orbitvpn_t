from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Promocode, PromocodeUsage, User
from .db import get_session
from app.utils.logging import get_logger

LOG = get_logger(__name__)


class PromocodeRepository:
    """
    Repository for managing promocodes and their usage.

    This repository can work in two modes:
    1. Standalone mode: Creates and manages its own database sessions (session=None)
    2. Transactional mode: Uses provided session for atomic operations (session provided)
    """

    def __init__(self, session: Optional[AsyncSession] = None, redis_client=None):
        """
        Initialize repository.

        Args:
            session: Optional SQLAlchemy async session. If None, repository creates its own sessions.
            redis_client: Redis client (currently unused by this repository)
        """
        self.session = session
        self.redis = redis_client
        self._owns_session = session is None
    """Repository for managing promocodes and their usage"""

    async def create_promocode(
        self,
        code: str,
        reward_type: str,
        reward_value: Decimal,
        creator_id: int,
        description: str = "",
        usage_limit: int = 0,
        expires_at: Optional[datetime] = None
    ) -> Optional[Promocode]:
        """
        Create a new promocode.

        Args:
            code: Promocode string (case-insensitive, will be stored in uppercase)
            reward_type: Type of reward ("balance_bonus_percent")
            reward_value: Bonus percentage (e.g., 10 for 10% bonus)
            creator_id: Admin who created the promocode
            description: Optional description
            usage_limit: Max uses (0 = unlimited)
            expires_at: Expiration datetime (None = never expires)

        Returns:
            Created Promocode or None if code already exists
        """
        async with get_session() as session:
            try:
                code_upper = code.upper().strip()

                promo = Promocode(
                    code=code_upper,
                    description=description,
                    created_at=datetime.utcnow(),
                    expires_at=expires_at,
                    usage_limit=usage_limit,
                    used_count=0,
                    reward_type=reward_type,
                    reward_value=reward_value,
                    creator_id=creator_id,
                    active=True
                )

                session.add(promo)
                await session.commit()
                await session.refresh(promo)

                LOG.info(f"Promocode created: {code_upper} by admin {creator_id}")
                return promo

            except IntegrityError:
                await session.rollback()
                LOG.warning(f"Promocode {code} already exists")
                return None
            except Exception as e:
                await session.rollback()
                LOG.error(f"Error creating promocode: {e}")
                return None

    async def get_promocode(self, code: str) -> Optional[Promocode]:
        """Get promocode by code (case-insensitive)"""
        async with get_session() as session:
            try:
                code_upper = code.upper().strip()
                stmt = select(Promocode).where(Promocode.code == code_upper)
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
            except Exception as e:
                LOG.error(f"Error getting promocode {code}: {e}")
                return None

    async def is_promocode_valid(self, code: str) -> tuple[bool, str]:
        """
        Check if promocode is valid for activation.

        Returns:
            (is_valid, error_message)
        """
        promo = await self.get_promocode(code)

        if not promo:
            return False, "promocode_not_found"

        if not promo.active:
            return False, "promocode_inactive"

        if promo.expires_at and datetime.utcnow() > promo.expires_at:
            return False, "promocode_expired"

        if promo.usage_limit > 0 and promo.used_count >= promo.usage_limit:
            return False, "promocode_limit_reached"

        return True, ""

    async def has_user_used_promocode(self, tg_id: int, promocode_id: int) -> bool:
        """Check if user has already used this promocode"""
        async with get_session() as session:
            try:
                stmt = select(PromocodeUsage).where(
                    PromocodeUsage.tg_id == tg_id,
                    PromocodeUsage.promocode_id == promocode_id
                )
                result = await session.execute(stmt)
                return result.scalar_one_or_none() is not None
            except Exception as e:
                LOG.error(f"Error checking promocode usage: {e}")
                return True  # Fail safe - prevent activation if we can't check

    async def activate_promocode(self, tg_id: int, code: str) -> tuple[bool, str, Optional[Promocode]]:
        """
        Activate a promocode for a user.

        Returns:
            (success, message_key, promocode)
        """
        # Check if promocode is valid
        is_valid, error = await self.is_promocode_valid(code)
        if not is_valid:
            return False, error, None

        promo = await self.get_promocode(code)

        # Check if user already used this promocode
        if await self.has_user_used_promocode(tg_id, promo.id):
            return False, "promocode_already_used", None

        # Record usage
        async with get_session() as session:
            try:
                usage = PromocodeUsage(
                    promocode_id=promo.id,
                    tg_id=tg_id,
                    activated_at=datetime.utcnow()
                )
                session.add(usage)

                # Increment used count
                stmt = (
                    update(Promocode)
                    .where(Promocode.id == promo.id)
                    .values(used_count=Promocode.used_count + 1)
                )
                await session.execute(stmt)

                await session.commit()

                LOG.info(f"User {tg_id} activated promocode {code}")
                return True, "promocode_activated", promo

            except Exception as e:
                await session.rollback()
                LOG.error(f"Error activating promocode: {e}")
                return False, "promocode_activation_error", None

    async def get_active_promocode_for_user(self, tg_id: int) -> Optional[Promocode]:
        """
        Get the currently active promocode for user (if any).
        User can have only one active promocode at a time.
        """
        try:
            # Get user's latest activated promocode
            stmt = (
                select(Promocode)
                .join(PromocodeUsage, PromocodeUsage.promocode_id == Promocode.id)
                .where(PromocodeUsage.tg_id == tg_id)
                .order_by(PromocodeUsage.activated_at.desc())
                .limit(1)
            )
            result = await self.session.execute(stmt)
            promo = result.scalar_one_or_none()

            if not promo:
                return None

            # Check if still valid
            if not promo.active:
                return None

            if promo.expires_at and datetime.utcnow() > promo.expires_at:
                return None

            return promo

        except Exception as e:
            LOG.error(f"Error getting active promocode for user {tg_id}: {e}")
            return None

    async def deactivate_promocode(self, code: str) -> bool:
        """Deactivate a promocode"""
        async with get_session() as session:
            try:
                code_upper = code.upper().strip()
                stmt = (
                    update(Promocode)
                    .where(Promocode.code == code_upper)
                    .values(active=False)
                )
                result = await session.execute(stmt)
                await session.commit()

                if result.rowcount > 0:
                    LOG.info(f"Promocode {code_upper} deactivated")
                    return True
                return False

            except Exception as e:
                await session.rollback()
                LOG.error(f"Error deactivating promocode: {e}")
                return False

    async def list_promocodes(self, active_only: bool = False) -> List[Promocode]:
        """List all promocodes"""
        async with get_session() as session:
            try:
                stmt = select(Promocode)
                if active_only:
                    stmt = stmt.where(Promocode.active == True)
                stmt = stmt.order_by(Promocode.created_at.desc())

                result = await session.execute(stmt)
                return list(result.scalars().all())
            except Exception as e:
                LOG.error(f"Error listing promocodes: {e}")
                return []

    async def get_promocode_stats(self, code: str) -> Optional[dict]:
        """Get usage statistics for a promocode"""
        promo = await self.get_promocode(code)
        if not promo:
            return None

        return {
            "code": promo.code,
            "description": promo.description,
            "reward_type": promo.reward_type,
            "reward_value": float(promo.reward_value),
            "used_count": promo.used_count,
            "usage_limit": promo.usage_limit,
            "active": promo.active,
            "created_at": promo.created_at,
            "expires_at": promo.expires_at
        }
