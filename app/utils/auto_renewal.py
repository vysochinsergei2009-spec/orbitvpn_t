import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import select
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from app.repo.db import get_session
from app.repo.models import User
from app.repo.user import UserRepository
from app.utils.redis import get_redis
from app.locales.locales import get_translator
from config import PLANS

LOG = logging.getLogger(__name__)


class AutoRenewalTask:
    """
    Background task that automatically renews subscriptions when:
    - Subscription expires in <= 1 day
    - User has sufficient balance
    - Balance >= cheapest plan price (1 month)

    Runs every 6 hours to check for users needing auto-renewal.
    """

    def __init__(self, bot: Bot, check_interval_seconds: int = 3600 * 6):
        """
        Args:
            bot: Aiogram Bot instance for sending notifications
            check_interval_seconds: How often to check (default: 6 hours)
        """
        self.bot = bot
        self.check_interval = check_interval_seconds
        self.task: asyncio.Task = None
        self._running = False

    async def _attempt_auto_renewal(self, user: User, redis) -> bool:
        """
        Attempt to auto-renew user subscription with 1-month plan.

        Args:
            user: User model instance
            redis: Redis client

        Returns:
            True if renewed successfully, False otherwise
        """
        try:
            # Get 1-month plan (most affordable)
            monthly_plan = PLANS['sub_1m']
            price = Decimal(str(monthly_plan['price']))
            days = monthly_plan['days']

            # Check if user has sufficient balance
            if user.balance < price:
                LOG.debug(f"User {user.tg_id} has insufficient balance for auto-renewal: {user.balance} < {price}")
                return False

            # Renew subscription
            async with get_session() as session:
                user_repo = UserRepository(session, redis)

                success = await user_repo.buy_subscription(
                    tg_id=user.tg_id,
                    days=days,
                    price=float(price)
                )

                if success:
                    LOG.info(f"Auto-renewed subscription for user {user.tg_id}: {days} days for {price} RUB")

                    # Send notification
                    try:
                        t = get_translator(user.lang)
                        new_balance = user.balance - price
                        sub_end = await user_repo.get_subscription_end(user.tg_id)
                        expire_date = datetime.fromtimestamp(sub_end).strftime('%Y.%m.%d')

                        message = t('auto_renewal_success',
                                   days=days,
                                   price=float(price),
                                   balance=float(new_balance),
                                   expire_date=expire_date)

                        await self.bot.send_message(chat_id=user.tg_id, text=message)
                    except (TelegramForbiddenError, TelegramBadRequest) as e:
                        LOG.warning(f"Could not notify user {user.tg_id} about auto-renewal: {e}")

                    return True
                else:
                    LOG.warning(f"Failed to auto-renew subscription for user {user.tg_id}")
                    return False

        except Exception as e:
            LOG.error(f"Error during auto-renewal for user {user.tg_id}: {type(e).__name__}: {e}")
            return False

    async def run_once(self):
        """Run a single auto-renewal check cycle"""
        try:
            redis = await get_redis()

            async with get_session() as session:
                # Get users whose subscription expires in <= 1 day
                now = datetime.utcnow()
                threshold = now + timedelta(days=1)

                result = await session.execute(
                    select(User).where(
                        User.subscription_end.isnot(None),
                        User.subscription_end <= threshold,  # Expires soon
                        User.subscription_end >= now  # Not yet expired
                    )
                )
                users = result.scalars().all()

                LOG.info(f"Checking {len(users)} users for auto-renewal eligibility")

                renewal_count = 0
                for user in users:
                    # Skip if balance too low (< monthly plan price)
                    monthly_price = Decimal(str(PLANS['sub_1m']['price']))
                    if user.balance < monthly_price:
                        continue

                    # Check if already auto-renewed today
                    redis_key = f"auto_renewal:{user.tg_id}:{now.strftime('%Y%m%d')}"
                    already_processed = await redis.get(redis_key)
                    if already_processed:
                        continue

                    # Attempt auto-renewal
                    success = await self._attempt_auto_renewal(user, redis)
                    if success:
                        renewal_count += 1
                        # Mark as processed for today
                        await redis.setex(redis_key, 86400, "1")

                LOG.info(f"Auto-renewal check completed: {renewal_count} subscriptions renewed")

        except Exception as e:
            LOG.error(f"Auto-renewal check error: {type(e).__name__}: {e}")

    async def run_loop(self):
        """Continuously run auto-renewal checks"""
        self._running = True
        LOG.info(f"Auto-renewal task started (interval: {self.check_interval}s)")

        while self._running:
            try:
                await self.run_once()
            except Exception as e:
                LOG.error(f"Error in auto-renewal loop: {type(e).__name__}: {e}")

            # Wait for next check
            await asyncio.sleep(self.check_interval)

        LOG.info("Auto-renewal task stopped")

    def start(self):
        """Start the background auto-renewal task"""
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.run_loop())
            LOG.info("Auto-renewal task created")
        else:
            LOG.warning("Auto-renewal task already running")

    def stop(self):
        """Stop the background auto-renewal task"""
        self._running = False
        if self.task and not self.task.done():
            self.task.cancel()
            LOG.info("Auto-renewal task cancelled")
