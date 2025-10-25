import asyncio
import logging
from datetime import datetime
from app.repo.db import get_session
from app.repo.payments import PaymentRepository
from app.utils.redis import get_redis

LOG = logging.getLogger(__name__)


class PaymentCleanupTask:
    def __init__(self, check_interval_seconds: int = 3600 * 2, cleanup_days: int = 7):
        self.check_interval = check_interval_seconds
        self.cleanup_days = cleanup_days
        self.task: asyncio.Task = None
        self._running = False

    async def run_once(self):
        """Run a single cleanup cycle"""
        try:
            async with get_session() as session:
                redis_client = await get_redis()
                payment_repo = PaymentRepository(session, redis_client)

                # Mark expired pending payments
                expired_count = await payment_repo.expire_old_payments()
                if expired_count > 0:
                    LOG.info(f"Marked {expired_count} payments as expired")

                # Clean up old expired/cancelled payments
                deleted_count = await payment_repo.cleanup_old_payments(days=self.cleanup_days)
                if deleted_count > 0:
                    LOG.info(f"Cleaned up {deleted_count} old expired/cancelled payments")

        except Exception as e:
            LOG.error(f"Payment cleanup error: {type(e).__name__}: {e}")

    async def run_loop(self):
        """Continuously run cleanup checks"""
        self._running = True
        LOG.info(f"Payment cleanup task started (interval: {self.check_interval}s, cleanup after: {self.cleanup_days} days)")

        while self._running:
            try:
                await self.run_once()
            except Exception as e:
                LOG.error(f"Error in payment cleanup loop: {type(e).__name__}: {e}")

            # Wait for next check
            await asyncio.sleep(self.check_interval)

        LOG.info("Payment cleanup task stopped")

    def start(self):
        """Start the background cleanup task"""
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.run_loop())
            LOG.info("Payment cleanup task created")
        else:
            LOG.warning("Payment cleanup task already running")

    def stop(self):
        """Stop the background cleanup task"""
        self._running = False
        if self.task and not self.task.done():
            self.task.cancel()
            LOG.info("Payment cleanup task cancelled")
