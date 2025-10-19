import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from app.payments.gateway.base import BasePaymentGateway
from app.payments.models import PaymentResult, PaymentMethod
from app.repo.payments import PaymentRepository
from config import TON_ADDRESS

LOG = logging.getLogger(__name__)

class TonGateway(BasePaymentGateway):
    requires_polling = True

    def __init__(self, session, redis_client=None):
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
        payment = await self.payment_repo.get_payment(payment_id)
        if not payment:
            LOG.warning(f"Payment {payment_id} not found")
            return False

        if not payment.get('comment') or not payment.get('expected_crypto_amount'):
            LOG.debug(f"TON payment {payment_id} incomplete: {payment}")
            return False

        tx = await self.payment_repo.get_pending_ton_transaction(
            comment=payment['comment'],
            amount=payment['expected_crypto_amount']
        )

        if not tx:
            return False

        # Prevent replay attacks: check if tx_hash already used for another payment
        if await self.payment_repo.is_tx_hash_already_used(tx.tx_hash):
            LOG.warning(f"TON transaction {tx.tx_hash} already used for another payment, rejecting replay")
            await self.payment_repo.mark_transaction_processed(tx.tx_hash)
            return False

        await self.payment_repo.mark_transaction_processed(tx.tx_hash)
        await self.payment_repo.update_payment_status(payment_id, "confirmed", tx.tx_hash)
        await self.on_payment_confirmed(payment_id, tx.tx_hash)
        LOG.info(f"TON payment confirmed: id={payment_id}, tx={tx.tx_hash}")
        return True

    async def on_payment_confirmed(self, payment_id: int, tx_hash: Optional[str] = None):
        LOG.info(f"TON payment confirmed callback: id={payment_id}, tx={tx_hash}")