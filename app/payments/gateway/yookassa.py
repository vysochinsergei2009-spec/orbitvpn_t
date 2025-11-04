import logging
from decimal import Decimal
from typing import Optional
from yookassa import Configuration, Payment as YooKassaPayment
from app.payments.gateway.base import BasePaymentGateway
from app.payments.models import PaymentResult, PaymentMethod
from app.repo.payments import PaymentRepository
from config import (
    YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY,
    YOOKASSA_TEST_SHOP_ID, YOOKASSA_TEST_SECRET_KEY,
    YOOKASSA_TESTNET
)

LOG = logging.getLogger(__name__)


class YooKassaGateway(BasePaymentGateway):
    requires_polling = True

    def __init__(self, session, redis_client=None):
        self.session = session
        self.payment_repo = PaymentRepository(session, redis_client)
        self._configured = False

    def _ensure_configured(self):
        """Configure YooKassa SDK with credentials based on test/production mode"""
        if not self._configured:
            # Select credentials based on testnet mode
            if YOOKASSA_TESTNET:
                shop_id = YOOKASSA_TEST_SHOP_ID
                secret_key = YOOKASSA_TEST_SECRET_KEY
                mode = "TESTNET"

                if not shop_id or not secret_key:
                    raise ValueError(
                        "YOOKASSA_TEST_SHOP_ID and YOOKASSA_TEST_SECRET_KEY must be configured in .env "
                        "when YOOKASSA_TESTNET=true"
                    )
            else:
                shop_id = YOOKASSA_SHOP_ID
                secret_key = YOOKASSA_SECRET_KEY
                mode = "PRODUCTION"

                if not shop_id or not secret_key:
                    raise ValueError(
                        "YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY must be configured in .env "
                        "when YOOKASSA_TESTNET=false"
                    )

            Configuration.configure(shop_id, secret_key)
            self._configured = True
            LOG.info(f"YooKassa configured successfully in {mode} mode (shop_id: {shop_id})")

    async def create_payment(
        self,
        t,
        tg_id: int,
        amount: Decimal,
        chat_id: Optional[int] = None,
        payment_id: Optional[int] = None,
        comment: Optional[str] = None
    ) -> PaymentResult:
        """Create YooKassa payment and return payment URL"""
        if payment_id is None:
            raise ValueError("payment_id is required for YooKassa")

        try:
            self._ensure_configured()

            # Get bot username for return URL
            from config import bot
            bot_info = await bot.get_me()
            bot_username = bot_info.username
            return_url = f"https://t.me/{bot_username}"

            # Create payment via YooKassa API
            payment_data = {
                "amount": {
                    "value": str(amount),
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": return_url
                },
                "capture": True,
                "description": comment or f"Payment #{payment_id}",
                "metadata": {
                    "payment_id": str(payment_id),
                    "tg_id": str(tg_id)
                },
                "receipt": {
                    "customer": {
                        "email": f"user{tg_id}@orbitvpn.com"  # Dummy email for receipt
                    },
                    "items": [
                        {
                            "description": "VPN subscription top-up",
                            "quantity": "1.00",
                            "amount": {
                                "value": str(amount),
                                "currency": "RUB"
                            },
                            "vat_code": 1,  # VAT 0% (no tax for digital services)
                            "payment_mode": "full_payment",
                            "payment_subject": "service"
                        }
                    ]
                }
            }

            yookassa_payment = YooKassaPayment.create(payment_data)

            # Store YooKassa payment ID in metadata
            await self.payment_repo.update_payment_metadata(
                payment_id=payment_id,
                metadata={'yookassa_payment_id': yookassa_payment.id}
            )

            # Get confirmation URL
            confirmation_url = yookassa_payment.confirmation.confirmation_url

            text = (
                t("yookassa_payment_intro") + "\n\n"
                + t("yookassa_amount", amount=amount) + "\n\n"
                + t("yookassa_click_button")
            )

            mode = "TESTNET" if YOOKASSA_TESTNET else "PRODUCTION"
            LOG.info(f"YooKassa payment created: payment_id={payment_id}, "
                    f"yookassa_id={yookassa_payment.id}, amount={amount}, mode={mode}")

            return PaymentResult(
                payment_id=payment_id,
                method=PaymentMethod.YOOKASSA,
                amount=amount,
                text=text,
                pay_url=confirmation_url
            )

        except Exception as e:
            LOG.error(f"Error creating YooKassa payment: {e}")
            raise ValueError(f"Failed to create YooKassa payment: {e}")

    async def check_payment(self, payment_id: int) -> bool:
        """
        Check if YooKassa payment has been paid.

        Uses database locks to prevent concurrent confirmations
        of the same payment from polling loop.
        """
        try:
            from app.repo.models import Payment as PaymentModel, User
            from sqlalchemy import select

            payment = await self.payment_repo.get_payment(payment_id)
            if not payment:
                LOG.warning(f"Payment {payment_id} not found")
                return False

            if payment.get('status') != 'pending':
                LOG.debug(f"YooKassa payment {payment_id} already {payment.get('status')}")
                return False

            extra_data = payment.get('extra_data', {})
            yookassa_payment_id = extra_data.get('yookassa_payment_id') if extra_data else None

            if not yookassa_payment_id:
                LOG.debug(f"YooKassa payment {payment_id} has no yookassa_payment_id")
                return False

            self._ensure_configured()

            # Get payment status from YooKassa
            yookassa_payment = YooKassaPayment.find_one(yookassa_payment_id)

            if not yookassa_payment:
                LOG.warning(f"YooKassa payment {yookassa_payment_id} not found")
                return False

            # Check if payment is succeeded
            if yookassa_payment.status == 'succeeded':
                # CRITICAL FIX: Lock payment AND user rows for atomic update
                result = await self.session.execute(
                    select(PaymentModel)
                    .where(PaymentModel.id == payment_id)
                    .with_for_update()
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

                # Check if tx_hash already set
                if payment_locked.tx_hash is not None:
                    LOG.warning(f"Payment {payment_id} already has tx_hash: {payment_locked.tx_hash}")
                    return False

                # ATOMIC UPDATE: Update payment status and balance
                from datetime import datetime
                old_balance = user.balance
                tx_hash = f"yookassa_{yookassa_payment_id}"

                payment_locked.status = 'confirmed'
                payment_locked.tx_hash = tx_hash
                payment_locked.confirmed_at = datetime.utcnow()
                user.balance += payment_locked.amount

                await self.session.commit()

                LOG.info(f"YooKassa payment confirmed: payment_id={payment_id}, user={user.tg_id}, "
                        f"amount={payment_locked.amount}, balance: {old_balance} → {user.balance}, "
                        f"yookassa_id={yookassa_payment_id}")

                # Invalidate cache (tolerate Redis failures)
                try:
                    redis = await self.payment_repo.get_redis()
                    await redis.delete(f"user:{user.tg_id}:balance")
                except Exception as e:
                    LOG.warning(f"Redis error invalidating cache for user {user.tg_id}: {e}")

                await self.on_payment_confirmed(payment_id, tx_hash)
                return True

            return False

        except Exception as e:
            LOG.error(f"Error checking YooKassa payment {payment_id}: {e}")
            return False

    async def on_payment_confirmed(self, payment_id: int, tx_hash: Optional[str] = None):
        """Callback when payment is confirmed"""
        LOG.info(f"YooKassa payment confirmed callback: id={payment_id}, tx={tx_hash}")
