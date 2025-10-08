import logging
from decimal import Decimal
from typing import Optional
from aiogram.types import LabeledPrice
from app.payments.gateway.base import BasePaymentGateway
from app.payments.models import PaymentResult, PaymentMethod
from config import TELEGRAM_STARS_RATE

LOG = logging.getLogger(__name__)

class TelegramStarsGateway(BasePaymentGateway):
    
    def __init__(self, bot):
        self.bot = bot

    @property
    def requires_polling(self) -> bool:
        return False

    async def create_payment(
        self,
        tg_id: int,
        amount: Decimal,
        chat_id: Optional[int] = None,
        payment_id: str = None,
        comment: str = None
    ) -> PaymentResult:
        if not chat_id:
            raise ValueError("chat_id required for Stars payment")
        
        stars_amount = int(amount / Decimal(TELEGRAM_STARS_RATE))
        payload = f"topup_{tg_id}_{int(amount)}"
        
        await self.bot.send_invoice(
            chat_id=chat_id,
            title="Пополнение OrbitVPN",
            description=f"Пополнение на {amount} RUB через Stars",
            payload=payload,
            currency="XTR",
            prices=[LabeledPrice(label="Сумма", amount=stars_amount)]
        )
        
        return PaymentResult(
            payment_id=payment_id or 0,
            method=PaymentMethod.STARS,
            amount=amount,
            text="⭐ Счет отправлен в чат"
        )

    async def check_payment(self, payment_id: int) -> bool:
        return False