import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from app.payments.gateway.base import BasePaymentGateway
from app.payments.models import PaymentResult, PaymentMethod
from app.repo.payments import PaymentRepository
from config import TON_ADDRESS

LOG = logging.getLogger(__name__)

class TonGateway(BasePaymentGateway):
    requires_polling = True

    def __init__(self, session, redis_client=None):
        self.session = session
        self.payment_repo = PaymentRepository(session, redis_client)

    async def create_payment(
        self,
        t,
        tg_id: int,
        amount: Decimal,
        chat_id: Optional[int] = None,
        payment_id: Optional[int] = None,
        comment: Optional[str] = None
    ) -> PaymentResult:
        if payment_id is None or comment is None:
            raise ValueError("payment_id and comment required for TON")

        from app.utils.rates import get_ton_price
        try:
            ton_price = await get_ton_price()
            expected_ton = (Decimal(amount) / ton_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except Exception as e:
            LOG.error(f"Error fetching TON price: {e}")
            raise ValueError("Failed to fetch TON price")

        wallet = TON_ADDRESS
        text = (
            t("ton_payment_intro") + "\n\n"
            + t("ton_send_amount", expected_ton=expected_ton, amount=amount) + "\n"
            + t("ton_wallet", wallet=wallet) + "\n\n"
            + t("ton_comment", comment=comment) + "\n\n"
            + t("ton_comment_warning")
        )

        return PaymentResult(
            payment_id=payment_id,
            method=PaymentMethod.TON,
            amount=amount,
            text=text,
            wallet=wallet,
            comment=comment,
            expected_crypto_amount=expected_ton
        )

    async def check_payment(self, payment_id: int) -> bool:
        """
        Check if TON payment has been confirmed on blockchain.

        CRITICAL FIX: Uses database locks to prevent replay attacks and race conditions
        where one TON transaction could confirm multiple payments.

        Returns:
            True if payment was confirmed successfully
        """
        from app.repo.models import Payment as PaymentModel, User
        from sqlalchemy import select

        # Get payment details
        payment = await self.payment_repo.get_payment(payment_id)
        if not payment:
            LOG.warning(f"Payment {payment_id} not found")
            return False

        if not payment.get('comment') or not payment.get('expected_crypto_amount'):
            LOG.debug(f"TON payment {payment_id} incomplete: {payment}")
            return False

        if payment.get('status') != 'pending':
            LOG.debug(f"TON payment {payment_id} already {payment.get('status')}")
            return False

        # CRITICAL FIX: Lock payment row AND user row to prevent concurrent confirmations
        result = await self.session.execute(
            select(PaymentModel)
            .where(PaymentModel.id == payment_id)
            .with_for_update()  # Lock payment row
        )
        payment_locked = result.scalar_one_or_none()

        if not payment_locked or payment_locked.status != 'pending':
            LOG.debug(f"Payment {payment_id} not pending or already confirmed")
            return False

        # Lock user row for atomic balance update
        result = await self.session.execute(
            select(User)
            .where(User.tg_id == payment_locked.tg_id)
            .with_for_update()
        )
        user = result.scalar_one_or_none()
        if not user:
            LOG.error(f"User {payment_locked.tg_id} not found for payment {payment_id}")
            return False

        # Find matching TON transaction
        tx = await self.payment_repo.get_pending_ton_transaction(
            comment=payment_locked.comment,
            amount=payment_locked.expected_crypto_amount
        )

        if not tx:
            return False

        # Check if tx_hash already used (should be prevented by unique constraint)
        if payment_locked.tx_hash is not None:
            LOG.warning(f"Payment {payment_id} already has tx_hash: {payment_locked.tx_hash}")
            return False

        # Check if this tx_hash is used by another payment
        result = await self.session.execute(
            select(PaymentModel)
            .where(PaymentModel.tx_hash == tx.tx_hash)
        )
        existing_payment = result.scalar_one_or_none()
        if existing_payment:
            LOG.warning(f"TON transaction {tx.tx_hash} already used for payment {existing_payment.id}")
            await self.payment_repo.mark_transaction_processed(tx.tx_hash)
            return False

        # ATOMIC UPDATE: Mark transaction processed, update payment, and credit balance
        from datetime import datetime
        old_balance = user.balance

        tx.processed_at = datetime.utcnow()
        payment_locked.status = 'confirmed'
        payment_locked.tx_hash = tx.tx_hash
        payment_locked.confirmed_at = datetime.utcnow()
        user.balance += payment_locked.amount

        await self.session.commit()

        LOG.info(f"TON payment confirmed: payment_id={payment_id}, user={user.tg_id}, "
                f"amount={payment_locked.amount}, balance: {old_balance} → {user.balance}, "
                f"tx_hash={tx.tx_hash}")

        # Invalidate cache (tolerate Redis failures)
        try:
            redis = await self.payment_repo.get_redis()
            await redis.delete(f"user:{user.tg_id}:balance")
        except Exception as e:
            LOG.warning(f"Redis error invalidating cache for user {user.tg_id}: {e}")

        await self.on_payment_confirmed(payment_id, tx.tx_hash)
        return True

    async def on_payment_confirmed(self, payment_id: int, tx_hash: Optional[str] = None):
        LOG.info(f"TON payment confirmed callback: id={payment_id}, tx={tx_hash}")