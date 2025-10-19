from decimal import Decimal
from typing import Optional, List, Dict
from app.utils.logging import get_logger
from .base import BaseRepository
from app.payments.models import PaymentMethod

LOG = get_logger(__name__)

class PaymentRepository(BaseRepository):
    
    async def create_payment(
        self, 
        tg_id: int, 
        method: PaymentMethod,
        amount: Decimal, 
        currency: str,
        status: str,
        comment: Optional[str] = None
    ) -> int:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            payment_id = await conn.fetchval(
                """INSERT INTO payments (tg_id, method, amount, currency, status, comment, created_at) 
                   VALUES ($1, $2, $3, $4, $5, $6, NOW()) RETURNING id""",
                tg_id, method.value, amount, currency, status, comment
            )
        return payment_id

    async def get_payment(self, payment_id: int) -> Optional[Dict]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM payments WHERE id=$1", payment_id)
        return dict(row) if row else None

    async def update_payment_status(
        self, 
        payment_id: int, 
        status: str,
        tx_hash: Optional[str] = None
    ):
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if status == "confirmed":
                await conn.execute(
                    """UPDATE payments SET status=$1, tx_hash=$2, confirmed_at=NOW() 
                       WHERE id=$3""",
                    status, tx_hash, payment_id
                )
            else:
                await conn.execute(
                    "UPDATE payments SET status=$1 WHERE id=$2",
                    status, payment_id
                )

    async def get_pending_payments(self, method: Optional[PaymentMethod] = None) -> List[Dict]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if method:
                rows = await conn.fetch(
                    "SELECT * FROM payments WHERE status='pending' AND method=$1 ORDER BY created_at",
                    method.value
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM payments WHERE status='pending' ORDER BY created_at"
                )
        return [dict(row) for row in rows]

    async def is_transaction_processed(self, tx_hash: str) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            exists = await conn.fetchval(
                "SELECT 1 FROM ton_transactions WHERE tx_hash=$1",
                tx_hash
            )
        return bool(exists)

    async def mark_transaction_processed(self, tx_hash: str):
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO ton_transactions (tx_hash, processed_at) VALUES ($1, NOW()) ON CONFLICT DO NOTHING",
                tx_hash
            )

    async def is_payment_processed(self, payment_id: str) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            exists = await conn.fetchval(
                "SELECT 1 FROM processed_payments WHERE payment_id=$1",
                payment_id
            )
        return bool(exists)

    async def mark_payment_processed(self, payment_id: str, tg_id: int, amount: Decimal) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                exists = await conn.fetchval(
                    "SELECT 1 FROM processed_payments WHERE payment_id=$1",
                    payment_id
                )
                if exists:
                    return False
                
                await conn.execute(
                    """INSERT INTO processed_payments (payment_id, tg_id, amount, processed_at) 
                       VALUES ($1, $2, $3, NOW())""",
                    payment_id, tg_id, amount
                )
        return True

    async def get_payment_by_comment(self, comment: str) -> Optional[Dict]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM payments WHERE comment=$1", comment)
        return dict(row) if row else None
