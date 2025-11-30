"""
Payment notification utilities for sending payment confirmation messages to users.
"""
import logging
from decimal import Decimal
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from app.locales.locales import get_translator
from app.core.keyboards import payment_success_actions

LOG = logging.getLogger(__name__)


async def send_payment_notification(
    bot: Bot,
    tg_id: int,
    amount: Decimal,
    lang: str = "ru",
    has_active_subscription: bool = False
):
    """
    Send payment confirmation notification to user.

    Args:
        bot: Aiogram Bot instance
        tg_id: User Telegram ID
        amount: Total amount credited
        lang: User language (ru/en)
        has_active_subscription: Whether user has active subscription

    Returns:
        True if sent successfully, False otherwise
    """
    try:
        t = get_translator(lang)

        # Build success message
        success_text = t('payment_success', amount=float(amount))

        await bot.send_message(
            chat_id=tg_id,
            text=success_text,
            reply_markup=payment_success_actions(t, has_active_subscription)
        )

        LOG.info(f"Payment notification sent to user {tg_id}: {amount} RUB")
        return True

    except TelegramForbiddenError:
        LOG.warning(f"User {tg_id} blocked the bot, cannot send payment notification")
        return False
    except TelegramBadRequest as e:
        LOG.warning(f"Bad request sending payment notification to {tg_id}: {e}")
        return False
    except Exception as e:
        LOG.error(f"Error sending payment notification to {tg_id}: {type(e).__name__}: {e}")
        return False
