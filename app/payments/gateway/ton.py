import logging
from decimal import Decimal
from typing import Optional
from app.payments.gateway.base import BasePaymentGateway
from app.payments.models import PaymentResult, PaymentMethod
from app.repo.payments import PaymentRepository

LOG = logging.getLogger(__name__)

from config import TON_ADDRESS, TON_EXPLORER_TX_URL

class TonGateway(BasePaymentGateway):
    def __init__(self):
        self.payment_repo = PaymentRepository()

    @property
    def requires_polling(self) -> bool:
        return True

    async def create_payment(
        self,
        tg_id: int,
        amount: Decimal,
        chat_id: Optional[int] = None,
        payment_id: Optional[int] = None,
        comment: Optional[str] = None
    ) -> PaymentResult:
        if payment_id is None:
            raise ValueError("payment_id is required for TON payments")

        if comment is None:
            raise ValueError("comment is required for TON payments")

        wallet = TON_ADDRESS
        from app.utils.rates import get_ton_price

        ton_price = await get_ton_price()
        ton_amount = round(float(amount) / ton_price, 2)

        text = (
            f"Оплата через TON\n\n"
            f"Отправьте **{ton_amount} TON** (~{amount} RUB) на кошелек:\n"
            f"`{wallet}`\n\n"
            f"Комментарий: `{comment}`\n\n"
            "Без точного комментария платёж не будет засчитан."
        )

        url = None
        if TON_EXPLORER_TX_URL:
            url = TON_EXPLORER_TX_URL

        return PaymentResult(
            payment_id=payment_id,
            method=PaymentMethod.TON,
            amount=amount,
            text=text,
            url=url,
            wallet=wallet,
            comment=comment
        )

    async def check_payment(self, payment_id: int) -> bool:
        payment = await self.payment_repo.get_payment(payment_id)
        if not payment:
            return False

        comment = payment.get("comment")
        if not comment:
            LOG.warning("TON payment without comment, skipping")
            return False

        pool = await self.payment_repo._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM ton_transactions WHERE comment=$1 AND amount=$2 ORDER BY created_at DESC LIMIT 1",
                comment, payment['amount']
            )

        if not row:
            return False

        tx_hash = row['tx_hash']
        await self.payment_repo.mark_transaction_processed(tx_hash)
        await self.payment_repo.update_payment_status(payment_id, "confirmed", tx_hash)
        await self.payment_repo.mark_payment_processed(str(payment_id), payment['tg_id'], payment['amount'])
        await self.on_payment_confirmed(payment_id, tx_hash)
        return True

    async def on_payment_confirmed(self, payment_id: int, tx_hash: Optional[str] = None):
        LOG.info(f"TON payment confirmed: id={payment_id}, tx={tx_hash}")