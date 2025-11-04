import logging
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
import asyncio
from app.payments.models import PaymentResult, PaymentMethod
from app.payments.gateway.base import BasePaymentGateway
from app.payments.gateway.ton import TonGateway
from app.payments.gateway.stars import TelegramStarsGateway
from app.payments.gateway.cryptobot import CryptoBotGateway
from app.payments.gateway.yookassa import YooKassaGateway
from app.repo.payments import PaymentRepository
from app.repo.user import UserRepository
from app.repo.db import get_session
from app.utils.redis import get_redis
from config import bot

LOG = logging.getLogger(__name__)

class PaymentManager:
    def __init__(self, session, redis_client=None):
        self.session = session
        self.redis_client = redis_client
        self.payment_repo = PaymentRepository(session, redis_client)
        self.gateways: dict[PaymentMethod, BasePaymentGateway] = {
            PaymentMethod.TON: TonGateway(session, redis_client),
            PaymentMethod.STARS: TelegramStarsGateway(bot, session, redis_client),
            PaymentMethod.CRYPTOBOT: CryptoBotGateway(session, redis_client),
            PaymentMethod.YOOKASSA: YooKassaGateway(session, redis_client),
        }
        self.user_repo = UserRepository(session, redis_client)
        self.polling_task: Optional[asyncio.Task] = None

    async def create_payment(
        self,
        t,
        tg_id: int,
        method: PaymentMethod,
        amount: Decimal,
        chat_id: Optional[int] = None,
        force_new: bool = False,
    ) -> PaymentResult:
        try:
            from app.repo.models import User
            from sqlalchemy import select

            # CRITICAL FIX: Lock user row BEFORE checking for active payments
            # This prevents race condition where two concurrent requests both pass
            # the check and create duplicate payments
            result = await self.session.execute(
                select(User)
                .where(User.tg_id == tg_id)
                .with_for_update()  # Serialize payment creation per user
            )
            user = result.scalar_one_or_none()
            if not user:
                raise ValueError(f"User {tg_id} not found")

            # Check for active pending payments unless force_new=True
            if not force_new:
                active_payments = await self.payment_repo.get_active_pending_payments(tg_id)
                if active_payments:
                    # If there's an active payment, raise exception with payment details
                    active = active_payments[0]
                    raise ValueError(f"active_payment:{active['id']}:{active['amount']}:{active['method']}")

            currency = "RUB"
            comment = None
            expected_crypto_amount = None

            if method == PaymentMethod.TON:
                comment = uuid.uuid4().hex[:10]
                from app.utils.rates import get_ton_price
                ton_price = await get_ton_price()
                expected_crypto_amount = (Decimal(amount) / ton_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            payment_id = await self.payment_repo.create_payment(
                tg_id=tg_id,
                method=method.value,
                amount=amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                currency=currency,
                comment=comment,
                expected_crypto_amount=expected_crypto_amount
            )

            gateway = self.gateways[method]
            result = await gateway.create_payment(
                t,
                tg_id=tg_id,
                amount=amount,
                chat_id=chat_id,
                payment_id=payment_id,
                comment=comment
            )

            LOG.info(f"Payment created: {method} for user {tg_id}, amount {amount}, id={payment_id}")
            if method in [PaymentMethod.TON, PaymentMethod.CRYPTOBOT, PaymentMethod.YOOKASSA]:
                await self.start_polling_if_needed()
            return result
        except Exception as e:
            LOG.error(f"Create payment error for user {tg_id}: {type(e).__name__}: {e}")
            raise

    async def confirm_payment(self, payment_id: int, tg_id: int, amount: Decimal, tx_hash: Optional[str] = None):
        try:
            await self.user_repo.change_balance(tg_id, amount)
            if tx_hash:
                await self.payment_repo.update_payment_status(payment_id, "confirmed", tx_hash)
            LOG.info(f"Payment {payment_id} confirmed: +{amount} for user {tg_id}, tx={tx_hash}")
        except Exception as e:
            LOG.error(f"Confirm payment error for user {tg_id}: {type(e).__name__}: {e}")
            raise

    async def start_polling_if_needed(self):
        if self.polling_task is None or self.polling_task.done():
            self.polling_task = asyncio.create_task(self.run_polling_loop())

    async def run_polling_loop(self):
        while True:
            try:
                # Create new session for each polling iteration
                async with get_session() as session:
                    redis_client = await get_redis()
                    temp_payment_repo = PaymentRepository(session, redis_client)

                    # Check TON payments
                    ton_pendings = await temp_payment_repo.get_pending_payments(PaymentMethod.TON.value)
                    if ton_pendings:
                        from app.utils.updater import TonTransactionsUpdater
                        updater = TonTransactionsUpdater()
                        await updater.run_once()

                    # Check CryptoBot payments
                    cryptobot_pendings = await temp_payment_repo.get_pending_payments(PaymentMethod.CRYPTOBOT.value)
                    if cryptobot_pendings:
                        for payment in cryptobot_pendings:
                            # Create new session for each check
                            async with get_session() as check_session:
                                check_redis = await get_redis()
                                check_gateway = self.gateways[PaymentMethod.CRYPTOBOT].__class__(check_session, check_redis)
                                await check_gateway.check_payment(payment['id'])

                    # Check YooKassa payments
                    yookassa_pendings = await temp_payment_repo.get_pending_payments(PaymentMethod.YOOKASSA.value)
                    if yookassa_pendings:
                        for payment in yookassa_pendings:
                            # Create new session for each check
                            async with get_session() as check_session:
                                check_redis = await get_redis()
                                check_gateway = self.gateways[PaymentMethod.YOOKASSA].__class__(check_session, check_redis)
                                await check_gateway.check_payment(payment['id'])

                    # If no pending payments, stop polling
                    if not ton_pendings and not cryptobot_pendings and not yookassa_pendings:
                        break
            except Exception as e:
                LOG.error(f"Polling loop error: {type(e).__name__}: {e}")
            await asyncio.sleep(60)

    async def check_payment(self, payment_id: int) -> bool:
        try:
            payment = await self.payment_repo.get_payment(payment_id)
            if not payment or payment['status'] != 'pending':
                return False

            gateway = self.gateways[PaymentMethod(payment['method'])]
            confirmed = await gateway.check_payment(payment_id)

            # NOTE: TON and CryptoBot gateways handle balance updates internally
            # to maintain atomicity with transaction locks. Only call confirm_payment
            # for gateways that don't do this (currently: Stars via webhook)
            # For TON/CryptoBot, check_payment() already updated balance + payment status

            # Don't double-credit: TON and CryptoBot already updated balance in check_payment()
            # if confirmed and payment['method'] not in ['ton', 'cryptobot']:
            #     await self.confirm_payment(payment_id, payment['tg_id'], payment['amount'])

            return confirmed
        except Exception as e:
            LOG.error(f"Check payment error for payment {payment_id}: {type(e).__name__}: {e}")
            return False

    async def get_pending_payments(self, method: Optional[PaymentMethod | str] = None):
        return await self.payment_repo.get_pending_payments(method if method else None)

    async def close(self):
        for gateway in self.gateways.values():
            if hasattr(gateway, 'close'):
                await gateway.close()
        if self.polling_task:
            self.polling_task.cancel()