import asyncio
import logging
import random
from datetime import datetime, timedelta
from sqlalchemy import select
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from app.repo.db import get_session
from app.repo.models import User
from app.utils.redis import get_redis
from app.locales.locales import get_translator
from app.core.keyboards import balance_button_kb, get_renewal_notification_keyboard

LOG = logging.getLogger(__name__)


class SubscriptionNotificationTask:
    """
    Background task that checks for expiring subscriptions and sends notifications.

    Runs every 3 hours and sends:
    - 3-day warning when subscription expires in <= 3 days
    - 1-day warning when subscription expires in <= 1 day
    - Expired notification when subscription expired within last 24 hours

    Uses Redis to track sent notifications and avoid spam.
    All notifications include a Balance button to encourage renewal.
    """

    def __init__(self, bot: Bot, check_interval_seconds: int = 3600 * 3):
        """
        Args:
            bot: Aiogram Bot instance for sending messages
            check_interval_seconds: How often to check (default: 3 hours)
        """
        self.bot = bot
        self.check_interval = check_interval_seconds
        self.task: asyncio.Task = None
        self._running = False

    def _get_random_message(self, lang: str, days: int | str, user_balance: float = 0) -> str:
        """
        Get random notification message variant with pricing info.

        Args:
            lang: User language ('ru' or 'en')
            days: Days until expiry (3, 1) or 'expired'
            user_balance: User's current balance for 1-day warning

        Returns:
            Random message text
        """
        from config import PLANS
        t = get_translator(lang)

        if days == 3:
            variants = [
                t('sub_expiry_3days_1'),
                t('sub_expiry_3days_2'),
                t('sub_expiry_3days_3'),
            ]
        elif days == 1:
            # Add pricing info for last day warning
            monthly_price = PLANS['sub_1m']['price']
            needed = max(0, monthly_price - user_balance)

            variants = [
                t('sub_expiry_1day_1'),
                t('sub_expiry_1day_2'),
                t('sub_expiry_1day_3'),
            ]

            message = random.choice(variants)

            # Add quick renewal info
            if needed > 0:
                message += f"\n\n{t('quick_renewal_info', price=monthly_price, needed=int(needed))}"
            else:
                message += f"\n\n{t('quick_renewal_ready', price=monthly_price)}"

            return message

        elif days == 'expired':
            variants = [
                t('sub_expired_1'),
                t('sub_expired_2'),
                t('sub_expired_3'),
            ]
        else:
            return ""

        return random.choice(variants)

    async def _send_notification(self, tg_id: int, lang: str, days: int | str, user_balance: float = 0) -> bool:
        """
        Send subscription expiry notification to user.

        Args:
            tg_id: Telegram user ID
            lang: User language
            days: Days until expiry (3, 1) or 'expired'
            user_balance: User's current balance

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            message = self._get_random_message(lang, days, user_balance)
            if not message:
                return False

            t = get_translator(lang)
            # Use renewal keyboard with both "Renew" and "Balance" buttons
            keyboard = get_renewal_notification_keyboard(t)

            await self.bot.send_message(
                chat_id=tg_id,
                text=message,
                reply_markup=keyboard
            )

            LOG.info(f"Sent {days}-day expiry notification to user {tg_id}")
            return True

        except TelegramForbiddenError:
            LOG.warning(f"User {tg_id} blocked the bot")
            return False
        except TelegramBadRequest as e:
            LOG.warning(f"Bad request sending notification to {tg_id}: {e}")
            return False
        except Exception as e:
            LOG.error(f"Error sending notification to {tg_id}: {type(e).__name__}: {e}")
            return False

    async def _check_and_notify_user(self, user: User, redis):
        """
        Check if user needs notification and send if needed.

        Args:
            user: User model instance
            redis: Redis client
        """
        # Skip if notifications disabled
        if not user.notifications:
            return

        # Skip if no subscription
        if not user.subscription_end:
            return

        now = datetime.utcnow()
        time_left = user.subscription_end - now
        days_left = time_left.total_seconds() / 86400

        # Format subscription end date for Redis key
        sub_end_date = user.subscription_end.strftime('%Y%m%d')

        # Determine notification type based on days left
        if -1 <= days_left <= 0:
            # Subscription expired within last 24 hours
            notification_type = 'expired'
            days = 'expired'
            ttl = 86400 * 7  # 7 days TTL
        elif 0 < days_left <= 1:
            # 1 day warning
            notification_type = '1d'
            days = 1
            ttl = 86400 * 2  # 2 days TTL
        elif 1 < days_left <= 3:
            # 3 day warning
            notification_type = '3d'
            days = 3
            ttl = 86400 * 4  # 4 days TTL
        else:
            # Too far in future or expired too long ago
            return

        # Check if already sent
        redis_key = f"notif:{notification_type}:{user.tg_id}:{sub_end_date}"

        try:
            already_sent = await redis.get(redis_key)
            if already_sent:
                return  # Already sent this notification
        except Exception as e:
            LOG.warning(f"Redis error checking notification for {user.tg_id}: {e}")
            return

        # Send notification with user balance (for pricing info in 1-day warning)
        success = await self._send_notification(user.tg_id, user.lang, days, float(user.balance))

        # Mark as sent if successful
        if success:
            try:
                await redis.setex(redis_key, ttl, "1")
            except Exception as e:
                LOG.warning(f"Redis error marking notification sent for {user.tg_id}: {e}")

    async def run_once(self):
        """Run a single notification check cycle"""
        try:
            redis = await get_redis()

            async with get_session() as session:
                # Get all users with subscriptions expiring soon or recently expired
                now = datetime.utcnow()
                future_threshold = now + timedelta(days=3)  # Check up to 3 days in future
                past_threshold = now - timedelta(days=1)  # Check up to 1 day in past

                result = await session.execute(
                    select(User).where(
                        User.subscription_end.isnot(None),
                        User.subscription_end >= past_threshold,  # Include recently expired
                        User.subscription_end <= future_threshold  # Include soon to expire
                    )
                )
                users = result.scalars().all()

                LOG.info(f"Checking {len(users)} users for expiring/expired subscriptions")

                # Check each user
                for user in users:
                    await self._check_and_notify_user(user, redis)

                LOG.info("Subscription notification check completed")

        except Exception as e:
            LOG.error(f"Subscription notification check error: {type(e).__name__}: {e}")

    async def run_loop(self):
        """Continuously run notification checks"""
        self._running = True
        LOG.info(f"Subscription notification task started (interval: {self.check_interval}s)")

        while self._running:
            try:
                await self.run_once()
            except Exception as e:
                LOG.error(f"Error in subscription notification loop: {type(e).__name__}: {e}")

            # Wait for next check
            await asyncio.sleep(self.check_interval)

        LOG.info("Subscription notification task stopped")

    def start(self):
        """Start the background notification task"""
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.run_loop())
            LOG.info("Subscription notification task created")
        else:
            LOG.warning("Subscription notification task already running")

    def stop(self):
        """Stop the background notification task"""
        self._running = False
        if self.task and not self.task.done():
            self.task.cancel()
            LOG.info("Subscription notification task cancelled")
