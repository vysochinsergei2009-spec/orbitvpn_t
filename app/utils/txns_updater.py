import asyncio
from decimal import Decimal
from datetime import datetime, timedelta
from pytonapi import AsyncTonapi
from pytonapi.utils import to_amount, raw_to_userfriendly

from .db import init_db, get_pg_pool
from config import TON_ADDRESS, TONAPI_KEY


class TonTransactionsUpdater:
    def __init__(self, ton_address: str = TON_ADDRESS, api_key: str = TONAPI_KEY):
        self.ton_address = ton_address
        self.last_lt = 0
        self.tonapi = AsyncTonapi(api_key=api_key)

    async def fetch_new_transactions(self, limit: int = 50):
        try:
            result = await self.tonapi.blockchain.get_account_transactions(
                account_id=self.ton_address,
                limit=limit
            )

            txs = []
            now = datetime.utcnow()
            min_time = now - timedelta(minutes=10)

            for tx in result.transactions:
                lt = int(tx.lt)
                created_at = datetime.utcfromtimestamp(tx.utime)

                if lt <= self.last_lt or created_at < min_time:
                    continue

                self.last_lt = max(self.last_lt, lt)
                txs.append(tx)

            return txs

        except Exception as e:
            print(f"[TonTransactionsUpdater] fetch error: {e}")
            return []

    async def insert_transactions(self, txs):
        if not txs:
            return

        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            for tx in txs:
                try:
                    tx_hash = tx.hash
                    amount = Decimal(to_amount(tx.in_msg.value)).quantize(Decimal("0.000001"))

                    comment = ""
                    if getattr(tx.in_msg, "decoded_op_name", "") == "text_comment":
                        comment = tx.in_msg.decoded_body.get("text", "")

                    # --- чистый user-friendly sender ---
                    sender = None
                    source = getattr(tx.in_msg, "source", None)
                    if source:
                        try:
                            # если есть метод .to_userfriendly
                            sender = source.address.to_userfriendly()
                        except AttributeError:
                            # fallback на raw -> user-friendly
                            root = getattr(source.address, "root", None)
                            if root:
                                sender = raw_to_userfriendly(root)

                    created_at = datetime.utcfromtimestamp(tx.utime)

                    await conn.execute(
                        """
                        INSERT INTO ton_transactions(tx_hash, amount, comment, sender, created_at, processed_at)
                        VALUES($1, $2, $3, $4, $5, NULL)
                        ON CONFLICT (tx_hash) DO NOTHING
                        """,
                        tx_hash, amount, comment, sender, created_at
                    )

                except Exception as e:
                    print(f"[TonTransactionsUpdater] insert error: {e}")

    async def run_once(self):
        txs = await self.fetch_new_transactions()
        await self.insert_transactions(txs)

    async def run_loop(self, interval: int = 60):
        while True:
            try:
                await self.run_once()
            except Exception as e:
                print(f"[TonTransactionsUpdater] loop error: {e}")
            await asyncio.sleep(interval)


if __name__ == "__main__":
    async def main_loop():
        await init_db()
        updater = TonTransactionsUpdater()
        await updater.run_loop(interval=60)

    asyncio.run(main_loop())