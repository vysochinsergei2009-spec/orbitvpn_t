from decimal import Decimal
from typing import Optional, List, Dict, Union
from datetime import datetime, timedelta

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.payments.models import PaymentMethod
from app.repo.models import Payment as PaymentModel, TonTransaction
from .db import get_session
from app.utils.logging import get_logger
from .base import BaseRepository
from config import PAYMENT_TIMEOUT_MINUTES

LOG = get_logger(__name__)


class PaymentRepository(BaseRepository):
    async def create_payment(
        self,
        tg_id: int,
        method: str,
        amount: Decimal,
        currency: str,
        status: str = 'pending',
        comment: Optional[str] = None,
        expected_crypto_amount: Optional[Decimal] = None
    ) -> int:
        payment = PaymentModel(
            tg_id=tg_id,
            method=method,
            amount=amount,
            currency=currency,
            status=status,
            comment=comment,
            expected_crypto_amount=expected_crypto_amount
        )
        self.session.add(payment)
        await self.session.commit()
        await self.session.refresh(payment)
        return payment.id

    async def get_payment(self, payment_id: int) -> Optional[Dict]:
        result = await self.session.execute(select(PaymentModel).where(PaymentModel.id == payment_id))
        payment = result.scalar_one_or_none()
        return payment.__dict__ if payment else None

    async def update_payment_status(
        self,
        payment_id: int,
        status: str,
        tx_hash: Optional[str] = None
    ):
        stmt = update(PaymentModel).where(PaymentModel.id == payment_id).values(status=status)
        if status == 'confirmed':
            stmt = stmt.values(tx_hash=tx_hash, confirmed_at=datetime.utcnow())
        await self.session.execute(stmt)
        await self.session.commit()

    async def get_pending_payments(
        self,
        method: Optional[Union[str, PaymentMethod]] = None
    ) -> List[Dict]:
        query = select(PaymentModel).where(PaymentModel.status == 'pending')
        if method:
            m = method.value if isinstance(method, PaymentMethod) else method
            query = query.where(PaymentModel.method == m)
        query = query.order_by(PaymentModel.created_at)
        result = await self.session.execute(query)
        payments = result.scalars().all()
        return [p.__dict__ for p in payments]

    async def mark_transaction_processed(self, tx_hash: str):
        stmt = update(TonTransaction).where(TonTransaction.tx_hash == tx_hash).values(
            processed_at=datetime.utcnow()
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def mark_failed_old_payments(self):
        threshold = datetime.utcnow() - timedelta(minutes=PAYMENT_TIMEOUT_MINUTES)
        stmt = update(PaymentModel).where(
            PaymentModel.status == 'pending',
            PaymentModel.created_at < threshold
        ).values(status='expired')
        await self.session.execute(stmt)
        await self.session.commit()

    async def mark_payment_processed(self, payment_id: str, tg_id: int, amount: Decimal) -> bool:
        """Mark Telegram Stars payment as processed"""
        result = await self.session.execute(
            select(PaymentModel).where(
                PaymentModel.tx_hash == payment_id,
                PaymentModel.tg_id == tg_id,
                PaymentModel.status == 'pending'
            )
        )
        payment = result.scalar_one_or_none()
        if not payment:
            LOG.warning(f"Payment {payment_id} not found or already processed for user {tg_id}")
            return False

        payment.status = 'confirmed'
        payment.confirmed_at = datetime.utcnow()
        await self.session.commit()
        LOG.info(f"Payment {payment_id} marked as processed for user {tg_id}, amount {amount}")
        return True

    async def mark_payment_processed_with_lock(self, payment_id: str, tg_id: int, amount: Decimal) -> bool:
        """Mark Telegram Stars payment as processed with database lock to prevent race conditions"""
        result = await self.session.execute(
            select(PaymentModel).where(
                PaymentModel.tx_hash == payment_id,
                PaymentModel.tg_id == tg_id,
                PaymentModel.status == 'pending'
            ).with_for_update()
        )
        payment = result.scalar_one_or_none()
        if not payment:
            LOG.warning(f"Payment {payment_id} not found or already processed for user {tg_id}")
            return False

        payment.status = 'confirmed'
        payment.confirmed_at = datetime.utcnow()
        await self.session.commit()
        LOG.info(f"Payment {payment_id} marked as processed for user {tg_id}, amount {amount}")
        return True

    async def get_pending_ton_transaction(self, comment: str, amount: Decimal) -> Optional[TonTransaction]:
        """Get pending TON transaction by comment and amount"""
        result = await self.session.execute(
            select(TonTransaction).where(
                TonTransaction.comment == comment,
                TonTransaction.amount >= amount * Decimal("0.95"),
                TonTransaction.processed_at == None
            ).order_by(TonTransaction.created_at.desc())
        )
        return result.scalar_one_or_none()

    async def is_tx_hash_already_used(self, tx_hash: str) -> bool:
        """Check if a transaction hash has already been used for a confirmed payment"""
        result = await self.session.execute(
            select(PaymentModel).where(
                PaymentModel.tx_hash == tx_hash,
                PaymentModel.status == 'confirmed'
            )
        )
        return result.scalar_one_or_none() is not None