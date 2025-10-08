import logging

import asyncio
from aiogram import Dispatcher
from aiohttp import web

from app.core.handlers import router
from app.locales.locales_mw import LocaleMiddleware
from app.utils.db import init_db, close_db
from app.utils.redis import init_cache, close_cache
from app.utils.rate_limit import RateLimitMiddleware, cleanup_rate_limit
from app.payments.watcher import PaymentWatcher
from config import bot


logging.basicConfig(level=logging.INFO)

async def main():
    await init_db()
    await init_cache()

    dp = Dispatcher()

    dp.include_router(router)
    dp.message.middleware(LocaleMiddleware())
    dp.callback_query.middleware(LocaleMiddleware())
    
    watcher = PaymentWatcher(interval=60)

    limiter = RateLimitMiddleware(
        default_limit=0.8,
        custom_limits={
            '/start': 3.0,
        }
    )

    dp.message.middleware(limiter)
    dp.callback_query.middleware(limiter)

    cleanup_task = asyncio.create_task(cleanup_rate_limit(limiter, interval=3600, max_age=3600))

    print("Bot started...")
    try:
        await watcher.start()
        await dp.start_polling(bot)
    finally:
        cleanup_task.cancel()
        try:
            await watcher.stop()
            await cleanup_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()
        await close_db()
        await close_cache()

if __name__ == "__main__":
    asyncio.run(main())