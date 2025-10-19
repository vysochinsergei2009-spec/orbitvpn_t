from datetime import datetime
from decimal import Decimal
from typing import Callable, Optional

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery, ContentType
from aiogram.filters.state import State, StatesGroup, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardMarkup, InlineKeyboardButton

from app.core.keyboards import (
    main_kb, balance_kb, set_kb, myvpn_kb, actions_kb,
    get_language_keyboard, instruction_kb, sub_kb,
    get_payment_methods_keyboard, get_referral_keyboard, back_balance
)
from app.repo.user import UserRepository
from app.repo.server import ServerRepository
from app.repo.payments import PaymentRepository
from app.payments.manager import PaymentManager
from app.payments.models import PaymentMethod
from app.repo.db import get_session
from app.utils.logging import get_logger
from app.utils.redis import get_redis
from config import FREE_TRIAL_DAYS, TELEGRAM_STARS_RATE, TON_RUB_RATE, PLANS, bot

router = Router()
LOG = get_logger(__name__)


class PaymentState(StatesGroup):
    waiting_amount = State()
    method = State()

async def get_repositories(session=None):
    redis_client = await get_redis()
    if session:
        return (
            UserRepository(session, redis_client),
            ServerRepository(redis_client),
            PaymentRepository(session, redis_client)
        )
    return redis_client


def extract_referrer_id(text: str) -> Optional[int]:
    parts = text.split()
    if len(parts) > 1 and parts[1].startswith("ref_"):
        try:
            return int(parts[1].split("_")[1])
        except (IndexError, ValueError):
            pass
    return None


def format_expire_date(timestamp: float, format_str: str = '%Y.%m.%d') -> str:
    return datetime.fromtimestamp(timestamp).strftime(format_str)


async def get_user_balance(user_repo: UserRepository, tg_id: int) -> float:
    return float(await user_repo.get_balance(tg_id))


async def update_configs_view(
    callback: CallbackQuery,
    t: Callable,
    user_repo: UserRepository,
    tg_id: int,
    custom_text: Optional[str] = None
):
    configs = await user_repo.get_configs(tg_id)
    has_active_sub = await user_repo.has_active_subscription(tg_id)

    if custom_text:
        text = custom_text
    elif has_active_sub:
        sub_end = await user_repo.get_subscription_end(tg_id)
        expire_date = format_expire_date(sub_end)
        text = t("your_configs_with_sub", expire_date=expire_date) if configs else t("no_configs_has_sub", expire_date=expire_date)
    else:
        text = t("your_configs") if configs else t("no_configs")

    await callback.message.edit_text(text, reply_markup=myvpn_kb(t, configs, has_active_sub))

@router.message(CommandStart())
async def cmd_start(message: Message, t):
    tg_id = message.from_user.id
    username = message.from_user.username or f"unknown_{tg_id}"
    referrer_id = extract_referrer_id(message.text)

    async with get_session() as session:
        user_repo, _, _ = await get_repositories(session)

        if await user_repo.add_if_not_exists(tg_id, username, referrer_id=referrer_id):
            await user_repo.buy_subscription(tg_id, days=FREE_TRIAL_DAYS, price=0.0)
            await message.answer(t("free_trial_activated"))

        await message.answer(t("cmd_start"), reply_markup=main_kb(t))


@router.callback_query(F.data == "myvpn")
async def myvpn_callback(callback: CallbackQuery, t):
    await callback.answer()

    async with get_session() as session:
        user_repo, _, _ = await get_repositories(session)
        await update_configs_view(callback, t, user_repo, callback.from_user.id)


@router.callback_query(F.data == "add_config")
async def add_config_callback(callback: CallbackQuery, t):
    tg_id = callback.from_user.id

    async with get_session() as session:
        user_repo, server_repo, _ = await get_repositories(session)

        server = await server_repo.get_best()
        if not server:
            await callback.answer(t('no_servers_or_cache_error'), show_alert=True)
            return

        await callback.answer(t('creating_config'))

        try:
            await user_repo.create_and_add_config(tg_id, server['id'])
            await server_repo.increment_users(server['id'])
            await update_configs_view(callback, t, user_repo, tg_id, t('config_created'))

        except ValueError as e:
            error_msg = str(e)
            if "No active subscription" in error_msg or "Subscription expired" in error_msg:
                await callback.message.edit_text(t('subscription_expired'), reply_markup=sub_kb(t))
            elif "Max configs reached" in error_msg:
                await callback.answer(t('max_configs_reached'), show_alert=True)
            else:
                LOG.error(f"ValueError creating config for user {tg_id}: {error_msg}")
                await callback.answer(t('error_creating_config'), show_alert=True)

        except Exception as e:
            LOG.error(f"Unexpected error creating config for user {tg_id}: {type(e).__name__}: {e}")
            await callback.answer(t('error_creating_config'), show_alert=True)


@router.callback_query(F.data.startswith("cfg_"))
async def config_selected(callback: CallbackQuery, t):
    await callback.answer()
    cfg_id = int(callback.data.split("_")[1])
    tg_id = callback.from_user.id

    async with get_session() as session:
        user_repo, _, _ = await get_repositories(session)
        configs = await user_repo.get_configs(tg_id)

        cfg = next((c for c in configs if c["id"] == cfg_id), None)
        if not cfg:
            await callback.message.edit_text(t('config_not_found'), reply_markup=actions_kb(t, cfg_id))
            return

        text = f"{t('your_config')}\n\n{t('config_selected')}\n<pre><code>{cfg['vless_link']}</code></pre>"
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=actions_kb(t, cfg_id))


@router.callback_query(F.data.startswith("delete_cfg_"))
async def config_delete(callback: CallbackQuery, t):
    cfg_id = int(callback.data.split("_")[2])
    tg_id = callback.from_user.id

    async with get_session() as session:
        user_repo, _, _ = await get_repositories(session)

        try:
            await user_repo.delete_config(cfg_id, tg_id)
            await callback.answer(t("config_deleted"))
            await update_configs_view(callback, t, user_repo, tg_id)

        except Exception as e:
            LOG.error(f"Error deleting config {cfg_id} for user {tg_id}: {type(e).__name__}: {e}")
            await callback.answer(t('error_deleting_config'), show_alert=True)


@router.callback_query(F.data == "buy_sub")
async def buy_sub_callback(callback: CallbackQuery, t):
    await callback.answer()
    tg_id = callback.from_user.id

    async with get_session() as session:
        user_repo, _, _ = await get_repositories(session)
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
        user_repo, _, _ = await get_repositories(session)
        balance = await user_repo.get_balance(tg_id)

        if balance < price:
            await callback.answer(t('low_balance'), show_alert=True)
            return

        if not await user_repo.buy_subscription(tg_id, days, price):
            LOG.error(f"Failed to buy subscription for user {tg_id}: plan {callback.data}")
            await callback.answer(t('error_buying_sub'), show_alert=True)
            return

        configs = await user_repo.get_configs(tg_id)
        await callback.answer(
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
    await callback.answer()
    tg_id = callback.from_user.id

    async with get_session() as session:
        user_repo, _, _ = await get_repositories(session)
        balance = await get_user_balance(user_repo, tg_id)

        await callback.message.edit_text(
            f"{t('extend_subscription')}\n\n{t('balance')}: {balance:.2f} RUB",
            reply_markup=sub_kb(t)
        )


@router.callback_query(F.data == 'balance')
async def balance_callback(callback: CallbackQuery, t, state: FSMContext):
    await callback.answer()
    await state.clear()
    tg_id = callback.from_user.id

    async with get_session() as session:
        user_repo, _, _ = await get_repositories(session)
        balance = await get_user_balance(user_repo, tg_id)

        await callback.message.edit_text(
            t('balance_text', balance=balance),
            reply_markup=balance_kb(t)
        )


@router.callback_query(F.data == 'add_funds')
async def add_funds_callback(callback: CallbackQuery, t):
    await callback.answer()
    await callback.message.edit_text(
        t('payment_method'),
        reply_markup=get_payment_methods_keyboard(t)
    )


@router.callback_query(F.data.startswith('pm_'))
async def payment_method_callback(callback: CallbackQuery, t, state: FSMContext):
    await callback.answer()
    method = callback.data.split('_')[1]

    await state.set_state(PaymentState.waiting_amount)
    await state.set_data({'method': method})
    await callback.message.edit_text(t('enter_amount'), reply_markup=back_balance(t))


@router.message(StateFilter(PaymentState.waiting_amount))
async def process_amount(message: Message, state: FSMContext, t):
    tg_id = message.from_user.id

    try:
        amount = Decimal(message.text)
        if amount < 200:
            raise ValueError("Amount too low")
        if amount > 100000:
            raise ValueError("Amount too high")
        # Check for overflow and invalid decimal values
        if amount.as_tuple().exponent < -2:
            raise ValueError("Too many decimal places")
    except (ValueError, TypeError) as e:
        LOG.error(f"Invalid amount input by user {tg_id}: {message.text} - {e}")
        await message.answer(t('invalid_amount'))
        return

    data = await state.get_data()
    try:
        method = PaymentMethod(data['method'])
    except ValueError:
        LOG.error(f"Invalid payment method for user {tg_id}: {data['method']}")
        await message.answer(t('invalid_payment_method'))
        await state.clear()
        return

    async with get_session() as session:
        try:
            redis_client = await get_redis()
            manager = PaymentManager(session, redis_client)
            result = await manager.create_payment(
                t,
                tg_id=tg_id,
                method=method,
                amount=amount,
                chat_id=message.chat.id if method == PaymentMethod.STARS else None
            )

            if method == PaymentMethod.TON:
                text = t(
                    'ton_payment_instruction',
                    ton_amount=f'<b>{result.expected_crypto_amount} TON</b>',
                    wallet=f"<pre><code>{result.wallet}</code></pre>",
                    comment=f'<pre>{result.comment}</pre>'
                )
                await message.answer(text, parse_mode="HTML")

            elif method == PaymentMethod.STARS and result.url:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💳 Оплатить", url=result.url)]
                ])
                await message.answer(result.text, reply_markup=kb)

            await state.clear()

        except Exception as e:
            LOG.error(f"Payment creation error for user {tg_id}: {type(e).__name__}: {e}")
            await message.answer(t('error_creating_payment'))
            await state.clear()


@router.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    payload = pre_checkout_query.invoice_payload

    # Basic format validation
    if not payload.startswith("topup_"):
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=False,
            error_message="Invalid payment format"
        )
        return

    # Validate payload format: topup_{tg_id}_{amount}
    try:
        parts = payload.split("_")
        if len(parts) != 3:
            raise ValueError("Invalid payload structure")
        tg_id = int(parts[1])
        amount = int(parts[2])

        # Verify the payment is for the requesting user
        if tg_id != pre_checkout_query.from_user.id:
            LOG.warning(f"User {pre_checkout_query.from_user.id} tried to pay for user {tg_id}")
            await bot.answer_pre_checkout_query(
                pre_checkout_query.id,
                ok=False,
                error_message="Invalid payment recipient"
            )
            return

        # Validate amount bounds
        if amount < 200 or amount > 100000:
            await bot.answer_pre_checkout_query(
                pre_checkout_query.id,
                ok=False,
                error_message="Invalid payment amount"
            )
            return

        await bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=True
        )

    except (ValueError, IndexError) as e:
        LOG.error(f"Pre-checkout validation failed for payload {payload}: {e}")
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=False,
            error_message="Invalid payment data"
        )


@router.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def successful_payment(message: Message, t):
    tg_id = message.from_user.id
    payment_id = message.successful_payment.telegram_payment_charge_id
    stars_paid = message.successful_payment.total_amount
    rub_amount = Decimal(stars_paid) * Decimal(str(TELEGRAM_STARS_RATE))

    async with get_session() as session:
        user_repo, _, payment_repo = await get_repositories(session)

        # Use database lock to prevent race conditions with duplicate payment events
        if await payment_repo.mark_payment_processed_with_lock(payment_id, tg_id, rub_amount):
            await user_repo.change_balance(tg_id, rub_amount)
            await message.answer(t('payment_success', amount=float(rub_amount)))
        else:
            await message.answer(t('payment_already_processed'))


@router.callback_query(F.data == 'back_main')
async def back_to_main(callback: CallbackQuery, t):
    await callback.answer()
    await callback.message.edit_text(t('welcome'), reply_markup=main_kb(t))


@router.callback_query(F.data == 'instruction')
async def instruction_callback(callback: CallbackQuery, t):
    await callback.answer()
    await callback.message.edit_text(
        t("instruction_text"),
        parse_mode="HTML",
        reply_markup=instruction_kb(t)
    )


@router.callback_query(F.data == 'settings')
async def settings_callback(callback: CallbackQuery, t):
    await callback.answer()
    await callback.message.edit_text(t("settings_text"), reply_markup=set_kb(t))


@router.callback_query(F.data == 'change_lang')
async def change_lang_callback(callback: CallbackQuery, t):
    await callback.answer()
    await callback.message.edit_text(
        t("choose_language"),
        reply_markup=get_language_keyboard(t)
    )


@router.callback_query(F.data.startswith("set_lang:"))
async def set_lang_callback(callback: CallbackQuery, t):
    lang = callback.data.split(":")[1]
    tg_id = callback.from_user.id

    async with get_session() as session:
        user_repo, _, _ = await get_repositories(session)
        await user_repo.set_lang(tg_id, lang)

    await callback.answer(t("language_updated"), show_alert=True)

    new_t = lambda key, **kwargs: t(key=key, lang=lang)
    await callback.message.edit_text(
        new_t("settings_text"),
        reply_markup=set_kb(new_t)
    )


@router.callback_query(F.data == 'referral')
async def referral(callback: CallbackQuery, t):
    """Display referral program information and link."""
    await callback.answer()
    tg_id = callback.from_user.id

    bot_username = (await callback.message.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{tg_id}"

    text = t('referral_text', ref_link=f"<pre><code>{ref_link}</code></pre>")
    await callback.message.edit_text(
        text,
        reply_markup=get_referral_keyboard(t, ref_link),
        parse_mode="HTML"
    )
