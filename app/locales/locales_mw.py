from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from app.repo.user import UserRepository
from app.locales.locales import t


class LocaleMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user:
            user_repo = UserRepository()
            lang = await user_repo.get_lang(tg_user.id)
        else:
            lang = "ru"

        data["lang"] = lang
        data["t"] = lambda key, **kwargs: t(lang=lang, key=key, **kwargs)

        return await handler(event, data)