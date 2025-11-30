from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional
from datetime import datetime
from app.payments.models import PaymentResult
from app.utils.logging import get_logger

LOG = get_logger(__name__)

class BasePaymentGateway(ABC):

    @abstractmethod
    async def create_payment(self, tg_id: int, amount: Decimal, chat_id: Optional[int] = None) -> PaymentResult:
        pass

    @abstractmethod
    async def check_payment(self, payment_id: int) -> bool:
        pass

    @property
    @abstractmethod
    def requires_polling(self) -> bool:
        pass

    async def on_payment_confirmed(self, payment_id: int, tx_hash: Optional[str] = None):
        pass

    async def _confirm_payment_atomic(
        self,
        payment_id: int,
        tx_hash: str,
        amount: Decimal,
        allow_expired: bool = False
    ) -> bool:
        """
        Atomically confirm payment with database locks to prevent race conditions.

        Args:
            payment_id: Payment ID to confirm
            tx_hash: Transaction hash (for deduplication)
            amount: Amount to credit
            allow_expired: Whether to allow confirming expired payments (for blockchain recovery)

        Returns:
            True if confirmed successfully, False otherwise
        """
        from app.repo.models import Payment as PaymentModel, User
        from sqlalchemy import select

        try:
            result = await self.session.execute(
                select(PaymentModel)
                .where(PaymentModel.id == payment_id)
                .with_for_update()
            )
            payment = result.scalar_one_or_none()

            if not payment:
                LOG.warning(f"Payment {payment_id} not found during confirmation")
                return False

            valid_statuses = ['pending', 'expired'] if allow_expired else ['pending']
            if payment.status not in valid_statuses:
                LOG.debug(f"Payment {payment_id} has status {payment.status}, cannot confirm")
                return False

            if payment.status == 'expired' and allow_expired:
                LOG.warning(f"Recovering expired payment {payment_id} - late confirmation")

            result = await self.session.execute(
                select(User)
                .where(User.tg_id == payment.tg_id)
                .with_for_update()
            )
            user = result.scalar_one_or_none()

            if not user:
                LOG.error(f"User {payment.tg_id} not found for payment {payment_id}")
                return False

            if payment.tx_hash is not None:
                LOG.warning(f"Payment {payment_id} already has tx_hash: {payment.tx_hash}")
                return False

            result = await self.session.execute(
                select(PaymentModel).where(PaymentModel.tx_hash == tx_hash)
            )
            existing_payment = result.scalar_one_or_none()
            if existing_payment:
                LOG.warning(f"Transaction {tx_hash} already used for payment {existing_payment.id}")
                return False

            old_balance = user.balance

            payment.status = 'confirmed'
            payment.tx_hash = tx_hash
            payment.confirmed_at = datetime.utcnow()
            user.balance += amount

            await self.session.commit()

            LOG.info(f"Payment confirmed: id={payment_id}, user={user.tg_id}, "
                    f"amount={amount}, balance: {old_balance} → {user.balance}, tx_hash={tx_hash}")

            try:
                redis = await self.get_redis()
                await redis.delete(f"user:{user.tg_id}:balance")
            except Exception as e:
                LOG.warning(f"Redis error invalidating cache for user {user.tg_id}: {e}")

            return True

        except Exception as e:
            await self.session.rollback()
            LOG.error(f"Error confirming payment {payment_id}: {type(e).__name__}: {e}")
            return False

    async def get_redis(self):
        """Get Redis client (must be implemented by subclass if needed)"""
        if hasattr(self, 'redis_client') and self.redis_client:
            return self.redis_client
        from app.utils.redis import get_redis
        return await get_redis()