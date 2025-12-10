import logging
import asyncio
import uuid
from decimal import Decimal
from typing import Optional
from aiogram import Bot
from yookassa import Configuration, Payment as YooKassaPayment
from urllib3.exceptions import ConnectTimeoutError, ReadTimeoutError, TimeoutError as Urllib3TimeoutError
from requests.exceptions import ConnectTimeout, ReadTimeout, Timeout as RequestsTimeout
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

    def __init__(self, session, redis_client=None, bot: Optional[Bot] = None):
        self.session = session
        self.payment_repo = PaymentRepository(session, redis_client)
        self._configured = False
        self.bot = bot

    async def _ensure_configured(self):
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

            await asyncio.to_thread(Configuration.configure, shop_id, secret_key)
            # Set timeout: 10s connect, 20s read (total 30s max)
            Configuration.timeout = 30
            self._configured = True
            LOG.info(f"YooKassa configured successfully in {mode} mode (shop_id: {shop_id}, timeout=30s)")

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
            await self._ensure_configured()

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
                        "email": f"user{tg_id}@orbitvpn.com"
                    },
                    "items": [
                        {
                            "description": "VPN subscription top-up",
                            "quantity": "1.00",
                            "amount": {
                                "value": str(amount),
                                "currency": "RUB"
                            },
                            "vat_code": 1,
                            "payment_mode": "full_payment",
                            "payment_subject": "service"
                        }
                    ]
                }
            }

            LOG.info(f"Creating YooKassa payment for user {tg_id}, amount={amount}, payment_id={payment_id}")
            
            # Retry logic with exponential backoff
            max_retries = 3
            last_error = None
            
            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        wait_time = 2 ** attempt  # Exponential backoff: 2s, 4s
                        LOG.warning(f"YooKassa API retry attempt {attempt + 1}/{max_retries} for payment {payment_id}, "
                                  f"waiting {wait_time}s before retry...")
                        await asyncio.sleep(wait_time)
                    
                    yookassa_payment = await asyncio.to_thread(YooKassaPayment.create, payment_data)
                    break  # Success, exit retry loop
                    
                except (ConnectTimeoutError, ReadTimeoutError, Urllib3TimeoutError,
                        ConnectTimeout, ReadTimeout, RequestsTimeout,
                        TimeoutError, asyncio.TimeoutError) as timeout_err:
                    last_error = timeout_err
                    error_type = type(timeout_err).__name__
                    LOG.warning(f"YooKassa API timeout (attempt {attempt + 1}/{max_retries}) for payment {payment_id}: "
                              f"{error_type}: {timeout_err}")
                    
                    if attempt == max_retries - 1:
                        # Last attempt failed
                        LOG.error(f"YooKassa API timeout after {max_retries} attempts for payment {payment_id}")
                        raise ValueError(f"YooKassa API timeout after {max_retries} attempts: {timeout_err}")
                    # Continue to next retry
                    
                except Exception as api_err:
                    # Non-timeout errors: don't retry, fail immediately
                    error_type = type(api_err).__name__
                    LOG.error(f"YooKassa API error (non-retryable) for payment {payment_id}: "
                            f"{error_type}: {api_err}")
                    raise ValueError(f"YooKassa API error: {api_err}")
            else:
                # All retries exhausted
                if last_error:
                    raise ValueError(f"YooKassa API failed after {max_retries} attempts: {last_error}")
                else:
                    raise ValueError("YooKassa API failed: unknown error")

            # Validate response
            if not yookassa_payment or not yookassa_payment.id:
                raise ValueError("YooKassa returned invalid payment response")

            if not hasattr(yookassa_payment, 'confirmation') or not yookassa_payment.confirmation:
                raise ValueError("YooKassa payment missing confirmation")

            confirmation_url = yookassa_payment.confirmation.confirmation_url
            if not confirmation_url:
                raise ValueError("YooKassa payment missing confirmation URL")

            # Store YooKassa payment ID in metadata
            await self.payment_repo.update_payment_metadata(
                payment_id=payment_id,
                metadata={'yookassa_payment_id': yookassa_payment.id}
            )

            text = (
                t("yookassa_payment_intro") + "\n\n"
                + t("yookassa_amount", amount=amount) + "\n\n"
                + t("yookassa_click_button")
            )

            mode = "TESTNET" if YOOKASSA_TESTNET else "PRODUCTION"
            LOG.info(f"YooKassa payment created successfully: payment_id={payment_id}, "
                    f"yookassa_id={yookassa_payment.id}, amount={amount}, "
                    f"url={confirmation_url}, mode={mode}")

            return PaymentResult(
                payment_id=payment_id,
                method=PaymentMethod.YOOKASSA,
                amount=amount,
                text=text,
                pay_url=confirmation_url
            )

        except ValueError as ve:
            # Re-raise ValueError as-is (already formatted)
            raise
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            LOG.error(f"Error creating YooKassa payment for user {tg_id}, payment_id={payment_id}, "
                     f"amount={amount}: {error_type}: {error_msg}", exc_info=True)
            raise ValueError(f"Failed to create YooKassa payment: {error_type}: {error_msg}")

    async def check_payment(self, payment_id: int) -> bool:
        """Check if YooKassa payment has been paid"""
        try:
            from app.repo.models import Payment as PaymentModel, User
            from sqlalchemy import select

            payment = await self.payment_repo.get_payment(payment_id)
            if not payment:
                LOG.warning(f"Payment {payment_id} not found")
                return False

            current_status = payment.get('status')
            if current_status == 'confirmed':
                LOG.debug(f"YooKassa payment {payment_id} already confirmed")
                return False

            if current_status not in ['pending', 'expired']:
                LOG.debug(f"YooKassa payment {payment_id} has status {current_status}, cannot process")
                return False

            extra_data = payment.get('extra_data', {})
            yookassa_payment_id = extra_data.get('yookassa_payment_id') if extra_data else None

            if not yookassa_payment_id:
                LOG.debug(f"YooKassa payment {payment_id} has no yookassa_payment_id")
                return False

            await self._ensure_configured()

            # Get payment status from YooKassa
            yookassa_payment = await asyncio.to_thread(YooKassaPayment.find_one, yookassa_payment_id)

            if not yookassa_payment:
                LOG.warning(f"YooKassa payment {yookassa_payment_id} not found")
                return False

            # Check if payment is succeeded
            if yookassa_payment.status == 'succeeded':
                result = await self.session.execute(
                    select(PaymentModel)
                    .where(PaymentModel.id == payment_id)
                    .with_for_update()
                )
                payment_locked = result.scalar_one_or_none()

                if not payment_locked:
                    LOG.debug(f"Payment {payment_id} not found during lock")
                    return False

                if payment_locked.status not in ['pending', 'expired']:
                    LOG.debug(f"Payment {payment_id} has status {payment_locked.status}, cannot confirm")
                    return False

                if payment_locked.status == 'expired':
                    LOG.warning(f"Recovering expired payment {payment_id}")

                result = await self.session.execute(
                    select(User)
                    .where(User.tg_id == payment_locked.tg_id)
                    .with_for_update()
                )
                user = result.scalar_one_or_none()
                if not user:
                    LOG.error(f"User {payment_locked.tg_id} not found for payment {payment_id}")
                    return False

                if payment_locked.tx_hash is not None:
                    LOG.warning(f"Payment {payment_id} already has tx_hash: {payment_locked.tx_hash}")
                    return False

                from datetime import datetime

                old_balance = user.balance
                tx_hash = f"yookassa_{yookassa_payment_id}"

                payment_locked.status = 'confirmed'
                payment_locked.tx_hash = tx_hash
                payment_locked.confirmed_at = datetime.utcnow()
                user.balance += payment_locked.amount

                await self.session.commit()

                LOG.info(f"YooKassa payment confirmed: payment_id={payment_id}, user={user.tg_id}, "
                        f"amount={payment_locked.amount}, balance: {old_balance} → {user.balance}")

                has_active_sub = user.subscription_end and user.subscription_end > datetime.utcnow()

                # Invalidate cache
                try:
                    redis = await self.payment_repo.get_redis()
                    await redis.delete(f"user:{user.tg_id}:balance")
                except Exception as e:
                    LOG.warning(f"Redis error invalidating cache for user {user.tg_id}: {e}")

                # Send notification
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
            LOG.error(f"Error checking YooKassa payment {payment_id}: {e}")
            return False

    async def cancel_payment(self, payment_id: int) -> bool:
        try:
            payment = await self.payment_repo.get_payment(payment_id)
            if not payment or payment.get('status') != 'pending':
                LOG.warning(f"Payment {payment_id} not found or not pending")
                return False

            extra_data = payment.get('extra_data')
            if not extra_data or not isinstance(extra_data, dict):
                LOG.warning(f"Payment {payment_id} has no valid extra_data")
                return True

            yookassa_payment_id = extra_data.get('yookassa_payment_id')

            if not yookassa_payment_id:
                LOG.warning(f"Payment {payment_id} has no yookassa_payment_id, skipping remote cancel")
                return True

            await self._ensure_configured()
            idempotency_key = uuid.uuid4()

            LOG.info(f"Cancelling YooKassa payment {yookassa_payment_id}")

            cancelled_payment = await asyncio.to_thread(
                YooKassaPayment.cancel, yookassa_payment_id, idempotency_key
            )

            if getattr(cancelled_payment, 'status', None) == 'canceled':
                LOG.info(f"Successfully cancelled YooKassa payment {yookassa_payment_id}")
                return True
            else:
                LOG.warning(f"Could not cancel YooKassa payment {yookassa_payment_id}")
                return False

        except Exception as e:
            LOG.error(f"Error cancelling YooKassa payment {payment_id}: {e}", exc_info=True)
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
        """Send payment confirmation notification"""
        LOG.info(f"YooKassa payment confirmed: id={payment_id}, tx={tx_hash}")
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