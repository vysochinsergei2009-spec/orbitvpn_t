import asyncio
import time
from typing import Any, Callable, Dict, Tuple
from collections import OrderedDict
from aiogram import BaseMiddleware


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, default_limit: float = 1.5, custom_limits: Dict[str, float] | None = None, max_cache_size: int = 10000):
        super().__init__()
        self.default_limit = default_limit
        self.custom_limits = custom_limits or {}
        self.last_time: OrderedDict[Tuple[int, str], float] = OrderedDict()
        self.max_cache_size = max_cache_size  # Prevent unbounded memory growth
        self._lock = asyncio.Lock()

    def _get_key(self, event: Any) -> str:
        # Handle message commands
        text = getattr(event, "text", None)
        if isinstance(text, str) and text.startswith("/"):
            return text.split()[0]

        # Handle callback queries (for financial operations rate limiting)
        callback_data = getattr(event, "data", None)
        if callback_data:
            return callback_data

        return event.__class__.__name__

    async def __call__(self, handler: Callable, event: Any, data: dict):
        user = getattr(event, "from_user", None)
        user_id = getattr(user, "id", None)
        if user_id is None:
            return await handler(event, data)

        key = self._get_key(event)
        limit = self.custom_limits.get(key, self.default_limit)
        now = time.monotonic()
        lk = (user_id, key)

        async with self._lock:
            last = self.last_time.get(lk)
            if last is not None and (now - last) < limit:
                msg = None
                try:
                    t = data.get("t")
                    msg = t("too_fast") if t else "⏳ Too fast"
                except Exception:
                    msg = "⏳ Too fast"

                if hasattr(event, "answer") and "callback" in event.__class__.__name__.lower():
                    try:
                        await event.answer(msg, show_alert=False)
                    except Exception:
                        pass
                else:
                    try:
                        m = await event.answer(msg)
                        asyncio.create_task(self._safe_delete(m, delay=2))
                    except Exception:
                        pass
                return

            self.last_time[lk] = now

            # Enforce max cache size to prevent memory leak
            if len(self.last_time) > self.max_cache_size:
                # Remove oldest 10% of entries when limit exceeded
                remove_count = self.max_cache_size // 10
                for _ in range(remove_count):
                    self.last_time.popitem(last=False)

        return await handler(event, data)

    @staticmethod
    async def _safe_delete(message, delay: float = 2.0):
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except Exception:
            pass


async def cleanup_rate_limit(middleware: RateLimitMiddleware, interval: int = 600, max_age: int = 1800):
    """
    Periodically clean up old rate limit entries to prevent memory growth.

    Args:
        middleware: The RateLimitMiddleware instance to clean
        interval: How often to run cleanup (default: 600s = 10 minutes)
        max_age: Remove entries older than this (default: 1800s = 30 minutes)
    """
    try:
        while True:
            await asyncio.sleep(interval)
            cutoff = time.monotonic() - max_age
            async with middleware._lock:
                old_keys = [k for k, t in middleware.last_time.items() if t < cutoff]
                for k in old_keys:
                    middleware.last_time.pop(k, None)
    except asyncio.CancelledError:
        pass