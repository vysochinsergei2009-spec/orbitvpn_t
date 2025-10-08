from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional
from app.payments.models import PaymentResult

class BasePaymentGateway(ABC):
    
    @abstractmethod
    async def create_payment(self, tg_id: int, amount: Decimal, chat_id: Optional[int] = None) -> PaymentResult:
        """Создание платежа, возвращает данные для пользователя"""
        pass

    @abstractmethod
    async def check_payment(self, payment_id: int) -> bool:
        """Проверка статуса платежа, возвращает True если подтвержден"""
        pass

    @property
    @abstractmethod
    def requires_polling(self) -> bool:
        """Требуется ли polling для этого метода"""
        pass

    async def on_payment_confirmed(self, payment_id: int, tx_hash: Optional[str] = None):
        """Хук при подтверждении платежа"""
        pass