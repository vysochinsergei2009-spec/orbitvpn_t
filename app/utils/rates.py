from pycoingecko import CoinGeckoAPI

cg = CoinGeckoAPI()

async def get_ton_price() -> float:
    data = cg.get_price(ids="the-open-network", vs_currencies="rub")
    return data["the-open-network"]["rub"]