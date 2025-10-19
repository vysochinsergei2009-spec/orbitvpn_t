import asyncio
from aiogram import Dispatcher
from app.core.handlers import router
from app.locales.locales_mw import LocaleMiddleware
from app.utils.redis import init_cache, close_cache
from app.utils.rate_limit import RateLimitMiddleware, cleanup_rate_limit
from app.utils.logging import get_logger, setup_aiogram_logger
from app.repo.db import close_db
from config import bot

LOG = get_logger(__name__)

async def main():
    setup_aiogram_logger()

    await init_cache()

    dp = Dispatcher()
    dp.include_router(router)

    dp.message.middleware(LocaleMiddleware())
    dp.callback_query.middleware(LocaleMiddleware())

    limiter = RateLimitMiddleware(
        default_limit=0.8,
        custom_limits={
            '/start': 3.0,
            'add_funds': 5.0,  # Payment creation
            'pm_ton': 10.0,  # TON payment method selection
            'pm_stars': 10.0,  # Stars payment method selection
            'buy_sub': 3.0,  # Subscription purchase
            'sub_1m': 2.0,  # Individual subscription plans
            'sub_3m': 2.0,
            'sub_6m': 2.0,
            'sub_12m': 2.0,
        },
    )
    dp.message.middleware(limiter)
    dp.callback_query.middleware(limiter)

    cleanup_task = asyncio.create_task(
        cleanup_rate_limit(limiter, interval=3600, max_age=3600)
    )

    LOG.info("Bot started...")

    try:
        await dp.start_polling(bot)
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass

        await bot.session.close()
        await close_db()  # Close database connections
        await close_cache()
        LOG.info("Bot stopped cleanly")


if __name__ == "__main__":
    asyncio.run(main())