from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from datetime import datetime
from enum import Enum

class PaymentMethod(str, Enum):
    TON = "ton"
    STARS = "stars"
    CRYPTOBOT = "cryptobot"
    YOOKASSA = "yookassa"

class PaymentStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    EXPIRED = "expired"

@dataclass
class PaymentResult:
    payment_id: int
    method: PaymentMethod
    amount: Decimal
    text: str
    url: Optional[str] = None
    wallet: Optional[str] = None
    comment: Optional[str] = None
    expected_crypto_amount: Optional[Decimal] = None
    pay_url: Optional[str] = None  # For CryptoBot invoice URL
    invoice_id: Optional[str] = None  # For CryptoBot invoice tracking

@dataclass
class Payment:
    id: int
    tg_id: int
    method: PaymentMethod
    amount: Decimal
    currency: str
    status: PaymentStatus
    comment: Optional[str]
    tx_hash: Optional[str]
    created_at: datetime
    confirmed_at: Optional[datetime]
    expected_crypto_amount: Optional[Decimal] = None