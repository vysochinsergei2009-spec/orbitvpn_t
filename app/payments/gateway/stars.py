import logging
from decimal import Decimal
from typing import Optional
from aiogram.types import LabeledPrice
from app.payments.gateway.base import BasePaymentGateway
from app.payments.models import PaymentResult, PaymentMethod
from app.repo.payments import PaymentRepository
from config import TELEGRAM_STARS_RATE

LOG = logging.getLogger(__name__)

class TelegramStarsGateway(BasePaymentGateway):
    requires_polling = False

    def __init__(self, bot, session, redis_client=None):
        self.bot = bot
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
        if not chat_id:
            raise ValueError("chat_id required for Stars payment")

        stars_amount = int(amount / Decimal(str(TELEGRAM_STARS_RATE)))
        payload = f"topup_{tg_id}_{int(amount)}"

        try:
            await self.bot.send_invoice(
                chat_id=chat_id,
                title=t("stars_add_title"),
                description=t("stars_add_description", amount=amount),
                payload=payload,
                currency="XTR",
                prices=[LabeledPrice(label=t("stars_price_label"), amount=stars_amount)]
            )
        except Exception as e:
            LOG.error(f"Error sending invoice for user {tg_id}: {e}")
            raise

        return PaymentResult(
            payment_id=payment_id or 0,
            method=PaymentMethod.STARS,
            amount=amount,
            text=t("stars_invoice_sent")
        )

    async def check_payment(self, payment_id: int) -> bool:
        return False