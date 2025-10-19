from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from app.repo.user import UserRepository
from app.repo.db import get_session
from app.locales.locales import get_translator
from app.utils.redis import get_redis

class LocaleMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        lang = "ru"  # Default language

        if tg_user:
            # Try Redis first without opening DB session (performance optimization)
            redis_client = await get_redis()
            key = f"user:{tg_user.id}:lang"
            cached_lang = await redis_client.get(key)

            if cached_lang:
                # Cache hit - no DB session needed
                lang = cached_lang
            else:
                # Cache miss - open session only when necessary
                async with get_session() as session:
                    user_repo = UserRepository(session, redis_client)
                    lang = await user_repo.get_lang(tg_user.id)

        data["lang"] = lang
        data["t"] = get_translator(lang)

        return await handler(event, data)