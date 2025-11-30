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
        # Set expiration time for pending payments
        expires_at = None
        if status == 'pending':
            expires_at = datetime.utcnow() + timedelta(minutes=PAYMENT_TIMEOUT_MINUTES)

        payment = PaymentModel(
            tg_id=tg_id,
            method=method,
            amount=amount,
            currency=currency,
            status=status,
            comment=comment,
            expected_crypto_amount=expected_crypto_amount,
            expires_at=expires_at
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

    async def update_payment_metadata(self, payment_id: int, metadata: dict):
        """Update payment extra_data (e.g., CryptoBot invoice_id)"""
        stmt = update(PaymentModel).where(PaymentModel.id == payment_id).values(extra_data=metadata)
        await self.session.execute(stmt)
        await self.session.commit()

    async def cancel_payment(self, payment_id: int) -> bool:
        """
        Cancel a pending payment

        IMPORTANT: For YooKassa/CryptoBot, checks if payment is already succeeded
        before cancellation to prevent loss of user funds
        """
        # Get payment details first
        result = await self.session.execute(
            select(PaymentModel).where(PaymentModel.id == payment_id)
        )
        payment = result.scalar_one_or_none()

        if not payment or payment.status != 'pending':
            return False

        # For YooKassa/CryptoBot, check if payment is already succeeded on gateway side
        if payment.method in ['yookassa', 'cryptobot']:
            extra_data = payment.extra_data or {}

            if payment.method == 'yookassa':
                yookassa_payment_id = extra_data.get('yookassa_payment_id')
                if yookassa_payment_id:
                    # Check if payment is succeeded in YooKassa
                    try:
                        from yookassa import Payment as YooKassaPayment
                        yookassa_payment = YooKassaPayment.find_one(yookassa_payment_id)
                        if yookassa_payment and yookassa_payment.status == 'succeeded':
                            LOG.warning(f"Cannot cancel payment {payment_id}: already succeeded in YooKassa")
                            return False
                    except Exception as e:
                        LOG.error(f"Error checking YooKassa payment status: {e}")
                        # Don't cancel if we can't verify
                        return False

        # Safe to cancel
        stmt = update(PaymentModel).where(
            PaymentModel.id == payment_id,
            PaymentModel.status == 'pending'
        ).values(status='cancelled', confirmed_at=datetime.utcnow())
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def get_active_pending_payments(self, tg_id: int) -> List[Dict]:
        """Get active (non-expired) pending payments for a user"""
        now = datetime.utcnow()
        query = select(PaymentModel).where(
            PaymentModel.tg_id == tg_id,
            PaymentModel.status == 'pending',
            PaymentModel.expires_at > now
        ).order_by(PaymentModel.created_at.desc())
        result = await self.session.execute(query)
        payments = result.scalars().all()
        return [p.__dict__ for p in payments]

    async def get_pending_or_recent_expired_payments(
        self,
        method: Optional[Union[str, PaymentMethod]] = None,
        expired_hours: int = 1
    ) -> List[Dict]:
        """
        Get pending payments AND recently expired payments (to catch late confirmations).

        This is critical for payment gateways like YooKassa where:
        - Local timeout is 10 minutes
        - Gateway timeout is 60 minutes
        - User might pay after local expiry but before gateway expiry

        Args:
            method: Payment method to filter by
            expired_hours: How many hours back to check expired payments
        """
        now = datetime.utcnow()
        expired_threshold = now - timedelta(hours=expired_hours)

        # Get pending payments
        query_pending = select(PaymentModel).where(PaymentModel.status == 'pending')

        # Get recently expired payments (created within last N hours)
        query_expired = select(PaymentModel).where(
            PaymentModel.status == 'expired',
            PaymentModel.created_at > expired_threshold
        )

        if method:
            m = method.value if isinstance(method, PaymentMethod) else method
            query_pending = query_pending.where(PaymentModel.method == m)
            query_expired = query_expired.where(PaymentModel.method == m)

        # Execute both queries
        result_pending = await self.session.execute(query_pending.order_by(PaymentModel.created_at))
        result_expired = await self.session.execute(query_expired.order_by(PaymentModel.created_at))

        pending_payments = result_pending.scalars().all()
        expired_payments = result_expired.scalars().all()

        all_payments = list(pending_payments) + list(expired_payments)
        return [p.__dict__ for p in all_payments]

    async def expire_old_payments(self) -> int:
        """Mark expired pending payments as expired"""
        now = datetime.utcnow()
        stmt = update(PaymentModel).where(
            PaymentModel.status == 'pending',
            PaymentModel.expires_at < now
        ).values(status='expired')
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount

    async def cleanup_old_payments(self, days: int = 7) -> int:
        """Delete old expired/cancelled payments (older than specified days)"""
        threshold = datetime.utcnow() - timedelta(days=days)
        from sqlalchemy import delete
        stmt = delete(PaymentModel).where(
            PaymentModel.status.in_(['expired', 'cancelled']),
            PaymentModel.created_at < threshold
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount