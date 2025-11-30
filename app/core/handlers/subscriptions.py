from aiogram import Router, F
from aiogram.types import CallbackQuery

from app.core.keyboards import sub_kb, myvpn_kb
from app.repo.db import get_session
from app.utils.logging import get_logger
from config import PLANS
from .utils import safe_answer_callback, get_repositories, get_user_balance, format_expire_date

router = Router()
LOG = get_logger(__name__)


@router.callback_query(F.data == "buy_sub")
async def buy_sub_callback(callback: CallbackQuery, t):
    await safe_answer_callback(callback)
    tg_id = callback.from_user.id

    async with get_session() as session:
        user_repo, _ = await get_repositories(session)
        balance = await get_user_balance(user_repo, tg_id)

        sub_text = t("buy_sub_text")
        if await user_repo.has_active_subscription(tg_id):
            sub_end = await user_repo.get_subscription_end(tg_id)
            expire_date = format_expire_date(sub_end, '%Y-%m-%d %H:%M')
            sub_text += f"\n\n{t('current_sub_until', expire_date=expire_date)}"

        await callback.message.edit_text(
            f"{sub_text}\n\n{t('balance')}: {balance:.2f} RUB",
            reply_markup=sub_kb(t)
        )


@router.callback_query(F.data.in_({"sub_1m", "sub_3m", "sub_6m", "sub_12m"}))
async def sub_buy_callback(callback: CallbackQuery, t):
    plan = PLANS[callback.data]
    days, price = plan["days"], plan["price"]
    tg_id = callback.from_user.id

    async with get_session() as session:
        user_repo, _ = await get_repositories(session)
        balance = await user_repo.get_balance(tg_id)

        if balance < price:
            await safe_answer_callback(callback, t('low_balance'), show_alert=True)
            return

        if not await user_repo.buy_subscription(tg_id, days, price):
            LOG.error(f"Failed to buy subscription for user {tg_id}: plan {callback.data}")
            await safe_answer_callback(callback, t('error_buying_sub'), show_alert=True)
            return

        configs = await user_repo.get_configs(tg_id)
        await safe_answer_callback(
            callback,
            t('sub_purchased_create_config') if not configs else t('sub_purchased'),
            show_alert=True
        )

        if configs:
            sub_end = await user_repo.get_subscription_end(tg_id)
            expire_date = format_expire_date(sub_end, '%Y-%m-%d %H:%M')
            await callback.message.edit_text(
                t('sub_success_with_expire', expire_date=expire_date),
                reply_markup=myvpn_kb(t, configs, True)
            )
        else:
            await callback.message.edit_text(
                t('create_first_config'),
                reply_markup=myvpn_kb(t, [], True)
            )


@router.callback_query(F.data == "renew_subscription")
async def renew_subscription_callback(callback: CallbackQuery, t):
    await safe_answer_callback(callback)
    tg_id = callback.from_user.id

    async with get_session() as session:
        user_repo, _ = await get_repositories(session)
        balance = await get_user_balance(user_repo, tg_id)
        sub_end = await user_repo.get_subscription_end(tg_id)
        has_active_sub = await user_repo.has_active_subscription(tg_id)

        if sub_end and has_active_sub:
            # Active subscription - show expiry date
            expire_date = format_expire_date(sub_end)
            text = f"{t('current_sub_until', expire_date=expire_date)}\n\n{t('extend_subscription')}\n\n{t('balance')}: {balance:.2f} RUB"
        else:
            # Expired or no subscription - show renewal message
            text = f"{t('extend_subscription')}\n\n{t('balance')}: {balance:.2f} RUB"

        await callback.message.edit_text(
            text,
            reply_markup=sub_kb(t, is_extension=True)
        )
