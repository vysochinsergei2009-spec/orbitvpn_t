from pathlib import Path
from typing import Optional

from telegraph import Telegraph
from telegraph.exceptions import TelegraphException

from config import TPH_TOKEN
from app.utils.redis import get_redis


class TelegraphManager:
    CACHE_TTL = 86400 * 30
    CACHE_KEY_PREFIX = "telegraph:install:"

    def __init__(self):
        try:
            self.telegraph = Telegraph(access_token=TPH_TOKEN)
        except TelegraphException as e:
            raise RuntimeError(f"Failed to initialize Telegraph: {e}")

    def _load_html_content(self, locale: str) -> str:
        current_dir = Path(__file__).parent
        file_path = current_dir / f"install_{locale}.html"

        if not file_path.exists():
            raise FileNotFoundError(f"Template not found: {file_path}")

        return file_path.read_text(encoding="utf-8")

    async def get_install_guide_url(self, locale: str = "ru") -> str:
        if locale not in ("ru", "en"):
            locale = "ru"

        cache_key = f"{self.CACHE_KEY_PREFIX}{locale}"
        try:
            redis = await get_redis()
            cached_url = await redis.get(cache_key)
            if cached_url:
                return cached_url
        except Exception as e:
            print(f"Redis cache read error: {e}")

        title = "Инструкция по установке VPN" if locale == "ru" else "VPN Installation Guide"
        author_name = "OrbitVPN"

        html_content = self._load_html_content(locale)

        try:
            response = self.telegraph.create_page(
                title=title,
                author_name=author_name,
                html_content=html_content
            )
            page_url = f"https://telegra.ph/{response['path']}"

            try:
                redis = await get_redis()
                await redis.setex(cache_key, self.CACHE_TTL, page_url)
            except Exception as e:
                print(f"Redis cache write error: {e}")

            return page_url

        except TelegraphException as e:
            raise RuntimeError(f"Failed to create Telegraph page: {e}")


_manager: Optional[TelegraphManager] = None


def get_telegraph_manager() -> TelegraphManager:
    global _manager
    if _manager is None:
        _manager = TelegraphManager()
    return _manager


async def get_install_guide_url(locale: str = "ru") -> str:
    manager = get_telegraph_manager()
    return await manager.get_install_guide_url(locale)