import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from aiogram import Bot
from app.payments.gateway.base import BasePaymentGateway
from app.payments.models import PaymentResult, PaymentMethod
from app.repo.payments import PaymentRepository
from config import TON_ADDRESS

LOG = logging.getLogger(__name__)

class TonGateway(BasePaymentGateway):
    requires_polling = True

    def __init__(self, session, redis_client=None, bot: Optional[Bot] = None):
        self.session = session
        self.payment_repo = PaymentRepository(session, redis_client)
        self.bot = bot

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
        Uses database locks to prevent replay attacks and race conditions.
        """
        payment = await self.payment_repo.get_payment(payment_id)
        if not payment:
            LOG.warning(f"Payment {payment_id} not found")
            return False

        if not payment.get('comment') or not payment.get('expected_crypto_amount'):
            LOG.debug(f"TON payment {payment_id} incomplete: {payment}")
            return False

        current_status = payment.get('status')
        if current_status == 'confirmed':
            LOG.debug(f"TON payment {payment_id} already confirmed")
            return False

        if current_status not in ['pending', 'expired']:
            LOG.debug(f"TON payment {payment_id} has status {current_status}, cannot process")
            return False

        tx = await self.payment_repo.get_pending_ton_transaction(
            comment=payment.get('comment'),
            amount=payment.get('expected_crypto_amount')
        )

        if not tx:
            return False

        from datetime import datetime
        tx.processed_at = datetime.utcnow()

        confirmed = await self._confirm_payment_atomic(
            payment_id=payment_id,
            tx_hash=tx.tx_hash,
            amount=payment['amount'],
            allow_expired=True
        )

        if confirmed:
            from app.repo.models import User
            from sqlalchemy import select

            async with self.session.begin():
                result = await self.session.execute(
                    select(User).where(User.tg_id == payment['tg_id'])
                )
                user = result.scalar_one_or_none()

                if user:
                    has_active_sub = user.subscription_end and user.subscription_end > datetime.utcnow()

                    await self.on_payment_confirmed(
                        payment_id=payment_id,
                        tx_hash=tx.tx_hash,
                        tg_id=user.tg_id,
                        total_amount=payment['amount'],
                        lang=user.lang,
                        promo_info=None,
                        has_active_subscription=has_active_sub
                    )

        return confirmed

    async def on_payment_confirmed(
        self,
        payment_id: int,
        tx_hash: Optional[str] = None,
        tg_id: Optional[int] = None,
        total_amount: Optional[Decimal] = None,
        lang: str = "ru",
        promo_info: Optional[dict] = None,
        has_active_subscription: bool = False
    ):
        """
        Callback when payment is confirmed.

        Sends Telegram notification to user about successful payment.
        """
        LOG.info(f"TON payment confirmed callback: id={payment_id}, tx={tx_hash}")

        # Send notification if bot is available and we have user info
        if self.bot and tg_id and total_amount:
            from app.utils.payment_notifications import send_payment_notification

            try:
                await send_payment_notification(
                    bot=self.bot,
                    tg_id=tg_id,
                    amount=total_amount,
                    lang=lang,
                    has_active_subscription=has_active_subscription,
                    promo_info=promo_info
                )
            except Exception as e:
                LOG.error(f"Error sending payment notification to {tg_id}: {e}")
                # Don't fail payment confirmation if notification fails