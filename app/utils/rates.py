from decimal import Decimal
from datetime import datetime, timedelta
import aiohttp

# Cache to avoid excessive API calls
_ton_price_cache = {"price": None, "timestamp": None}
_PRICE_CACHE_TTL_SECONDS = 60  # Cache for 1 minute

async def get_ton_price() -> Decimal:
    """Fetch TON price in RUB with caching and async HTTP"""
    now = datetime.utcnow()

    # Return cached price if still valid
    if (_ton_price_cache["price"] and
        _ton_price_cache["timestamp"] and
        (now - _ton_price_cache["timestamp"]).total_seconds() < _PRICE_CACHE_TTL_SECONDS):
        return _ton_price_cache["price"]

    # Fetch new price asynchronously
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "the-open-network", "vs_currencies": "rub"},
            timeout=aiohttp.ClientTimeout(total=5)
        ) as resp:
            data = await resp.json()
            price = Decimal(str(data["the-open-network"]["rub"]))

            # Update cache
            _ton_price_cache["price"] = price
            _ton_price_cache["timestamp"] = now

            return price