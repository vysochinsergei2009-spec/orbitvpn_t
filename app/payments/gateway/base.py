from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional
from app.payments.models import PaymentResult

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