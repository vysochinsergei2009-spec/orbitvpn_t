import logging
import uuid
from decimal import Decimal
from typing import Optional

from app.payments.models import PaymentResult, PaymentMethod
from app.payments.gateway.base import BasePaymentGateway
from app.payments.gateway.ton import TonGateway
from app.payments.gateway.stars import TelegramStarsGateway
from app.repo.payments import PaymentRepository
from app.repo.user import UserRepository


LOG = logging.getLogger(__name__)

class PaymentManager:
    def __init__(self):
        from config import bot
        self.gateways: dict[PaymentMethod, BasePaymentGateway] = {
            PaymentMethod.TON: TonGateway(),
            PaymentMethod.STARS: TelegramStarsGateway(bot),
        }
        self.payment_repo = PaymentRepository()
        self.user_repo = UserRepository()

    async def create_payment(
        self,
        tg_id: int,
        method: PaymentMethod,
        amount: Decimal,
        chat_id: Optional[int] = None,
        payment_id: str = None,
        comment: str = None
    ) -> PaymentResult:
        try:
            currency = "RUB"

            comment = None
            if method == PaymentMethod.TON:
                comment = uuid.uuid4().hex[:10]

            payment_id = await self.payment_repo.create_payment(
                tg_id=tg_id,
                method=method,
                amount=amount,
                currency=currency,
                status="pending",
                comment=comment
            )

            gateway = self.gateways[method]
            result = await gateway.create_payment(
                tg_id=tg_id,
                amount=amount,
                chat_id=chat_id,
                payment_id=payment_id,
                comment=comment
            )

            LOG.info(f"Payment created: {method} for user {tg_id}, amount {amount}, id={payment_id}")
            return result
        except Exception as e:
            LOG.exception(f"Create payment error: {e}")
            raise

    async def check_payment(self, payment_id: int) -> bool:
        try:
            payment = await self.payment_repo.get_payment(payment_id)
            if not payment:
                return False
            
            gateway = self.gateways[PaymentMethod(payment['method'])]
            confirmed = await gateway.check_payment(payment_id)
            
            if confirmed:
                await self.confirm_payment(payment_id, payment['tg_id'], payment['amount'])
            
            return confirmed
        except Exception as e:
            LOG.error(f"Check payment error: {e}")
            return False

    async def confirm_payment(self, payment_id: int, tg_id: int, amount: Decimal):
        try:
            await self.user_repo.change_balance(tg_id, amount)
            LOG.info(f"Payment {payment_id} confirmed: +{amount} for user {tg_id}")
        except Exception as e:
            LOG.error(f"Confirm payment error: {e}")
            raise

    async def get_pending_payments(self, method: Optional[PaymentMethod] = None):
        return await self.payment_repo.get_pending_payments(method)

    async def close(self):
        for gateway in self.gateways.values():
            if hasattr(gateway, 'close'):
                await gateway.close()
