import logging
from decimal import Decimal
from typing import Optional
from aiogram import Bot
from aiocryptopay import AioCryptoPay, Networks
from app.payments.gateway.base import BasePaymentGateway
from app.payments.models import PaymentResult, PaymentMethod
from app.repo.payments import PaymentRepository
from app.utils.rates import get_usdt_rub_rate
from config import CRYPTOBOT_TOKEN, CRYPTOBOT_TESTNET

LOG = logging.getLogger(__name__)


class CryptoBotGateway(BasePaymentGateway):
    requires_polling = True

    def __init__(self, session, redis_client=None, bot: Optional[Bot] = None):
        self.session = session
        self.payment_repo = PaymentRepository(session, redis_client)
        self._cryptopay: Optional[AioCryptoPay] = None
        self.bot = bot

    async def _get_cryptopay(self) -> AioCryptoPay:
        if self._cryptopay is None:
            if not CRYPTOBOT_TOKEN:
                raise ValueError("CRYPTOBOT_TOKEN is not configured in .env")

            network = Networks.TEST_NET if CRYPTOBOT_TESTNET else Networks.MAIN_NET
            self._cryptopay = AioCryptoPay(token=CRYPTOBOT_TOKEN, network=network)

        return self._cryptopay

    async def create_payment(
        self,
        t,
        tg_id: int,
        amount: Decimal,
        chat_id: Optional[int] = None,
        payment_id: Optional[int] = None,
        comment: Optional[str] = None
    ) -> PaymentResult:
        """Create CryptoBot invoice"""
        if payment_id is None:
            raise ValueError("payment_id is required for CryptoBot")

        try:
            cryptopay = await self._get_cryptopay()

            # Get current USDT/RUB exchange rate
            usdt_rate = await get_usdt_rub_rate()

            # Convert RUB to USDT
            usdt_amount = amount / usdt_rate

            LOG.info(f"Converting {amount} RUB to {usdt_amount:.2f} USDT (rate: {usdt_rate})")

            # Get bot username for callback URL
            profile = await cryptopay.get_me()
            bot_username = profile.payment_processing_bot_username

            invoice = await cryptopay.create_invoice(
                asset='USDT',
                amount=float(usdt_amount),  # Amount in USDT after conversion from RUB
                description=comment or f"Payment #{payment_id}",
                paid_btn_name="callback",  # Button to return to bot after payment
                paid_btn_url=f"https://t.me/{bot_username}",
                payload=str(payment_id),  # Used to identify payment in webhook
                allow_comments=False,
                allow_anonymous=False,
            )

            # Store invoice_id in payment metadata
            await self.payment_repo.update_payment_metadata(
                payment_id=payment_id,
                metadata={'invoice_id': invoice.invoice_id}
            )

            pay_url = invoice.bot_invoice_url

            text = (
                t("cryptobot_payment_intro") + "\n\n"
                + t("cryptobot_amount", amount=amount) + "\n"
                + f"≈ {usdt_amount:.2f} USDT\n\n"
                + t("cryptobot_click_button")
            )

            return PaymentResult(
                payment_id=payment_id,
                method=PaymentMethod.CRYPTOBOT,
                amount=amount,
                text=text,
                pay_url=pay_url,
                invoice_id=invoice.invoice_id
            )

        except Exception as e:
            LOG.error(f"Error creating CryptoBot invoice: {e}")
            raise ValueError(f"Failed to create CryptoBot invoice: {e}")

    async def check_payment(self, payment_id: int) -> bool:
        """
        Check if CryptoBot invoice has been paid.

        CRITICAL FIX: Uses database locks to prevent concurrent confirmations
        of the same payment from polling loop.
        """
        try:
            from app.repo.models import Payment as PaymentModel, User
            from sqlalchemy import select

            payment = await self.payment_repo.get_payment(payment_id)
            if not payment:
                LOG.warning(f"Payment {payment_id} not found")
                return False

            # CRITICAL FIX: Allow confirming expired payments if paid on CryptoBot side
            # This prevents loss of user funds when payment expires locally but succeeds on gateway
            current_status = payment.get('status')
            if current_status == 'confirmed':
                LOG.debug(f"CryptoBot payment {payment_id} already confirmed")
                return False

            # Allow processing for 'pending' and 'expired' statuses
            if current_status not in ['pending', 'expired']:
                LOG.debug(f"CryptoBot payment {payment_id} has status {current_status}, cannot process")
                return False

            extra_data = payment.get('extra_data', {})
            invoice_id = extra_data.get('invoice_id') if extra_data else None

            if not invoice_id:
                LOG.debug(f"CryptoBot payment {payment_id} has no invoice_id")
                return False

            cryptopay = await self._get_cryptopay()

            # Get invoice status from CryptoBot
            invoices = await cryptopay.get_invoices(invoice_ids=[invoice_id])

            if not invoices:
                LOG.warning(f"CryptoBot invoice {invoice_id} not found")
                return False

            invoice = invoices[0]

            # Check if invoice is paid
            if invoice.status == 'paid':
                # CRITICAL FIX: Lock payment AND user rows for atomic update
                result = await self.session.execute(
                    select(PaymentModel)
                    .where(PaymentModel.id == payment_id)
                    .with_for_update()
                )
                payment_locked = result.scalar_one_or_none()

                if not payment_locked:
                    LOG.debug(f"Payment {payment_id} not found during lock")
                    return False

                # Allow confirming if status is pending OR expired (but paid on gateway side)
                if payment_locked.status not in ['pending', 'expired']:
                    LOG.debug(f"Payment {payment_id} has status {payment_locked.status}, cannot confirm")
                    return False

                # Log if recovering expired payment
                if payment_locked.status == 'expired':
                    LOG.warning(f"Recovering expired payment {payment_id} - user paid after local timeout but succeeded on CryptoBot")

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

                # Check if tx_hash already set
                if payment_locked.tx_hash is not None:
                    LOG.warning(f"Payment {payment_id} already has tx_hash: {payment_locked.tx_hash}")
                    return False

                # ATOMIC UPDATE: Update payment status and balance
                from datetime import datetime

                old_balance = user.balance
                tx_hash = f"cryptobot_{invoice_id}"

                payment_locked.status = 'confirmed'
                payment_locked.tx_hash = tx_hash
                payment_locked.confirmed_at = datetime.utcnow()

                # Credit payment amount
                user.balance += payment_locked.amount

                await self.session.commit()

                LOG.info(f"CryptoBot payment confirmed: payment_id={payment_id}, user={user.tg_id}, "
                        f"amount={payment_locked.amount}, balance: {old_balance} → {user.balance}, "
                        f"invoice={invoice_id}")

                # Check subscription status BEFORE cache invalidation
                from datetime import datetime
                has_active_sub = user.subscription_end and user.subscription_end > datetime.utcnow()

                # Invalidate cache (tolerate Redis failures)
                try:
                    redis = await self.payment_repo.get_redis()
                    await redis.delete(f"user:{user.tg_id}:balance")
                except Exception as e:
                    LOG.warning(f"Redis error invalidating cache for user {user.tg_id}: {e}")

                # Send notification to user about successful payment
                await self.on_payment_confirmed(
                    payment_id=payment_id,
                    tx_hash=tx_hash,
                    tg_id=user.tg_id,
                    total_amount=payment_locked.amount,
                    lang=user.lang,
                    has_active_subscription=has_active_sub
                )
                return True

            return False

        except Exception as e:
            LOG.error(f"Error checking CryptoBot payment {payment_id}: {e}")
            return False

    async def on_payment_confirmed(
        self,
        payment_id: int,
        tx_hash: Optional[str] = None,
        tg_id: Optional[int] = None,
        total_amount: Optional[Decimal] = None,
        lang: str = "ru",
        has_active_subscription: bool = False
    ):
        """
        Callback when payment is confirmed.

        Sends Telegram notification to user about successful payment.
        """
        LOG.info(f"CryptoBot payment confirmed callback: id={payment_id}, tx={tx_hash}")

        # Send notification if bot is available and we have user info
        if self.bot and tg_id and total_amount:
            from app.utils.payment_notifications import send_payment_notification

            try:
                await send_payment_notification(
                    bot=self.bot,
                    tg_id=tg_id,
                    amount=total_amount,
                    lang=lang,
                    has_active_subscription=has_active_subscription
                )
            except Exception as e:
                LOG.error(f"Error sending payment notification to {tg_id}: {e}")
                # Don't fail payment confirmation if notification fails

    async def close(self):
        """Close CryptoPay client session"""
        if self._cryptopay:
            await self._cryptopay.close()
