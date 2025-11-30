import asyncio
from aiogram import Dispatcher
from app.core.handlers import router
from app.locales.locales_mw import LocaleMiddleware
from app.utils.redis import init_cache, close_cache
from app.utils.rate_limit import RateLimitMiddleware, cleanup_rate_limit
from app.utils.logging import get_logger, setup_aiogram_logger
from app.utils.payment_cleanup import PaymentCleanupTask
from app.utils.notifications import SubscriptionNotificationTask
from app.utils.config_cleanup import ConfigCleanupTask
from app.utils.auto_renewal import AutoRenewalTask
from app.repo.db import close_db
from app.repo.init_db import init_database
from config import bot

LOG = get_logger(__name__)

async def main():
    setup_aiogram_logger()

    await init_database()
    await init_cache()

    dp = Dispatcher()
    dp.include_router(router)

    dp.message.middleware(LocaleMiddleware())
    dp.callback_query.middleware(LocaleMiddleware())

    limiter = RateLimitMiddleware(
        default_limit=0.8,
        custom_limits={
            '/start': 3.0,
            'add_funds': 5.0,
            'pm_ton': 10.0,
            'pm_stars': 10.0,
            'buy_sub': 3.0,
            'sub_1m': 2.0,
            'sub_3m': 2.0,
            'sub_6m': 2.0,
            'sub_12m': 2.0,
        },
    )
    dp.message.middleware(limiter)
    dp.callback_query.middleware(limiter)

    rate_limit_cleanup_task = asyncio.create_task(
        cleanup_rate_limit(limiter, interval=3600, max_age=3600)
    )

    payment_cleanup = PaymentCleanupTask(check_interval_seconds=300, cleanup_days=7)
    payment_cleanup.start()

    subscription_notifications = SubscriptionNotificationTask(bot, check_interval_seconds=3600 * 3)
    subscription_notifications.start()

    # Start auto-renewal task (runs every 6 hours, renews subscriptions with sufficient balance)
    auto_renewal = AutoRenewalTask(bot, check_interval_seconds=3600 * 6)
    auto_renewal.start()

    # Start config cleanup task (runs once per week, removes configs expired >14 days)
    config_cleanup = ConfigCleanupTask(check_interval_seconds=86400 * 7, days_threshold=14)
    config_cleanup.start()

    LOG.info("Bot started...")

    try:
        await dp.start_polling(bot)
    finally:
        rate_limit_cleanup_task.cancel()
        payment_cleanup.stop()
        subscription_notifications.stop()
        auto_renewal.stop()
        config_cleanup.stop()

        try:
            await rate_limit_cleanup_task
        except asyncio.CancelledError:
            pass

        await bot.session.close()
        await close_db()
        await close_cache()
        LOG.info("Bot stopped cleanly")


if __name__ == "__main__":
    asyncio.run(main())