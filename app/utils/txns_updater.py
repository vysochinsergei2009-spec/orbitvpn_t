import asyncio
import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
from pytonapi import AsyncTonapi
from pytonapi.utils import to_amount, raw_to_userfriendly
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.repo.db import get_session
from app.payments.manager import PaymentManager
from app.payments.models import PaymentMethod
from app.repo.models import TonTransaction
from app.utils.redis import get_redis
from config import TON_ADDRESS, TONAPI_KEY, PAYMENT_TIMEOUT_MINUTES

LOG = logging.getLogger(__name__)

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
            min_time = now - timedelta(minutes=PAYMENT_TIMEOUT_MINUTES * 2)

            for tx in result.transactions:
                lt = int(tx.lt)
                try:
                    created_at = datetime.utcfromtimestamp(int(tx.utime))
                except Exception:
                    LOG.debug("Skipping tx with invalid utime: %s", getattr(tx, "hash", "<no-hash>"))
                    continue

                if lt <= self.last_lt or created_at < min_time:
                    continue
                self.last_lt = max(self.last_lt, lt)
                txs.append(tx)
            return txs
        except Exception as e:
            LOG.error(f"[TonTransactionsUpdater] fetch error: {e}")
            return []

    async def insert_transactions(self, txs):
        if not txs:
            return

        async with get_session() as session:
            for tx in txs:
                try:
                    tx_hash = tx.hash
                    amount = Decimal(to_amount(getattr(tx.in_msg, "value", 0))).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    comment = (
                        tx.in_msg.decoded_body.get("text", "")
                        if getattr(tx.in_msg, "decoded_op_name", "") == "text_comment"
                        else ""
                    )
                    source = getattr(tx.in_msg, "source", None)
                    sender = (
                        raw_to_userfriendly(source.address.root)
                        if source and hasattr(source, "address") and hasattr(source.address, "root")
                        else None
                    )
                    created_at = datetime.utcfromtimestamp(int(tx.utime))

                    txn = TonTransaction(
                        tx_hash=tx_hash,
                        amount=amount,
                        comment=comment,
                        sender=sender,
                        created_at=created_at,
                        processed_at=None
                    )
                    session.add(txn)
                except Exception as e:
                    LOG.error(f"[TonTransactionsUpdater] insert error: {e}")
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
            except Exception as e:
                LOG.error(f"[TonTransactionsUpdater] commit error: {e}")
                await session.rollback()

    async def process_pending_payments(self):
        async with get_session() as session:
            redis_client = await get_redis()
            manager = PaymentManager(session, redis_client)
            pendings = await manager.get_pending_payments(PaymentMethod.TON)
            for payment in pendings:
                try:
                    await manager.check_payment(payment['id'])
                except Exception as e:
                    LOG.error(f"[TonTransactionsUpdater] check_payment error: {e}")

    async def run_once(self):
        txs = await self.fetch_new_transactions()
        await self.insert_transactions(txs)
        await self.process_pending_payments()
        async with get_session() as session:
            redis_client = await get_redis()
            manager = PaymentManager(session, redis_client)
            try:
                await manager.payment_repo.mark_failed_old_payments()
            except Exception as e:
                LOG.error(f"[TonTransactionsUpdater] mark_failed_old_payments error: {e}")