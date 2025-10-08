import os
import asyncio
from tonclient.client import TonClient, DEVNET_BASE_URLS
from tonclient.types import ClientConfig
from decimal import Decimal
import asyncpg
from datetime import datetime

TON_ADDRESS = os.getenv('TON_ADDRESS')
DB_DSN = os.getenv('DATABASE_URL')

class TonTransactionsUpdater:
    def __init__(self, ton_address, db_dsn):
        self.ton_address = ton_address
        self.db_dsn = db_dsn
        self.last_lt = 0

    async def fetch_new_transactions(self):
        async with TonClient(config=ClientConfig(network={'server_address': DEVNET_BASE_URLS[0]})) as client:
            result = await client.net.query_collection(
                collection='transactions',
                filter={'account_addr': {'eq': self.ton_address}, 'lt': {'gt': self.last_lt}},
                result='id lt hash in_msg {source value text} created_at'
            )
            return result['result']

    async def insert_transactions(self, pool, txs):
        async with pool.acquire() as conn:
            for tx in txs:
                lt = int(tx['lt'])
                tx_hash = tx['hash']
                amount = Decimal(tx['in_msg']['value']) / 1e9
                comment = tx['in_msg'].get('text', '')
                sender = tx['in_msg']['source']
                created_at = datetime.fromtimestamp(tx['created_at'])
                await conn.execute(
                    '''
                    INSERT INTO ton_transactions(tx_hash, amount, comment, sender, created_at, processed_at)
                    VALUES($1, $2, $3, $4, $5, NULL)
                    ON CONFLICT (tx_hash) DO NOTHING
                    ''',
                    tx_hash, amount, comment, sender, created_at
                )
                self.last_lt = max(self.last_lt, lt)

    async def run(self):
        pool = await asyncpg.create_pool(self.db_dsn)
        while True:
            txs = await self.fetch_new_transactions()
            if txs:
                await self.insert_transactions(pool, txs)
            await asyncio.sleep(60)

if __name__ == '__main__':
    updater = TonTransactionsUpdater(TON_ADDRESS, DB_DSN)
    asyncio.run(updater.run())