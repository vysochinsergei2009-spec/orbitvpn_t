from datetime import datetime
from decimal import Decimal

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery, ContentType
from aiogram.filters.state import State, StatesGroup, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardMarkup, InlineKeyboardButton

from app.core.keyboards import (
    main_kb, 
    balance_kb,
    set_kb, 
    myvpn_kb,
    actions_kb, 
    get_language_keyboard,
    instruction_kb,
    sub_kb,
    get_payment_methods_keyboard,
    get_referral_keyboard
)
from app.repo.user import UserRepository
from app.repo.server import ServerRepository
from app.repo.payments import PaymentRepository
from app.payments.models import PaymentMethod
from app.payments.manager import PaymentManager
from app.utils.rates import get_ton_price
from app.utils.logging import get_logger

from config import FREE_TRIAL_DAYS, TELEGRAM_STARS_RATE, TON_RUB_RATE

router = Router()
LOG = get_logger(__name__)

class PaymentState(StatesGroup):
    waiting_amount = State()
    method = State()


@router.message(CommandStart())
async def cmd_start(message: Message, t, lang):
    tg_id = message.from_user.id
    username = message.from_user.username or f"unknown_{tg_id}"

    ref = (
        message.text.split(" ")[1]
        if len(message.text.split(" ")) > 1 and message.text.split(" ")[1].startswith("ref_")
        else None
    )
    referrer_id = int(ref.split("_")[1]) if ref else None

    user_repo = UserRepository()
    created = await user_repo.add_if_not_exists(tg_id, username, referrer_id=referrer_id)

    if created:
        await user_repo.buy_subscription(tg_id, days=FREE_TRIAL_DAYS, price=0.0)
        await message.answer(t("free_trial_activated"))

    await message.answer(t("cmd_start"), reply_markup=main_kb(t))


@router.callback_query(F.data == "myvpn")
async def myvpn_callback(callback: CallbackQuery, t):
    await callback.answer()
    tg_id = callback.from_user.id
    user_repo = UserRepository()
    configs = await user_repo.get_configs(tg_id)
    has_active_sub = await user_repo.has_active_subscription(tg_id)
    
    if has_active_sub:
        sub_end = await user_repo.get_subscription_end(tg_id)
        expire_date = datetime.fromtimestamp(sub_end).strftime('%Y.%m.%d')
        text = t("your_configs_with_sub", expire_date=expire_date) if configs else t("no_configs_has_sub", expire_date=expire_date)
    else:
        text = t("your_configs") if configs else t("no_configs")
    
    await callback.message.edit_text(text, reply_markup=myvpn_kb(t, configs, has_active_sub))

@router.callback_query(F.data == "add_config")
async def add_config_callback(callback: CallbackQuery, t):
    await callback.answer()
    tg_id = callback.from_user.id
    user_repo = UserRepository()
    server_repo = ServerRepository()

    server = await server_repo.get_best()
    if not server:
        await callback.answer(t('no_servers'), show_alert=True)
        return

    await callback.answer(t('creating_config'))
    try:
        config = await user_repo.create_and_add_config(tg_id, server['id'])
        await server_repo.increment_users(server['id'])

        configs = await user_repo.get_configs(tg_id)
        has_active_sub = await user_repo.has_active_subscription(tg_id)
        await callback.message.edit_text(
            t('config_created'),
            reply_markup=myvpn_kb(t, configs, has_active_sub)
        )

    except ValueError as e:
        msg = str(e)
        if "No active subscription" in msg or "Subscription expired" in msg:
            await callback.message.edit_text(t('subscription_expired'), reply_markup=sub_kb(t))
        elif "Max configs reached" in msg:
            await callback.answer(t('max_configs_reached'), show_alert=True)
        else:
            await callback.answer(t('error_creating_config'), show_alert=True)

    except Exception as e:
        LOG.error(e)
        await callback.answer(t('error_creating_config'), show_alert=True)


@router.callback_query(F.data == "buy_sub")
async def buy_sub_callback(callback: CallbackQuery, t):
    await callback.answer()
    tg_id = callback.from_user.id
    user_repo = UserRepository()
    balance = float(await user_repo.get_balance(tg_id))
    has_active_sub = await user_repo.has_active_subscription(tg_id)
    
    sub_text = t("buy_sub_text")
    if has_active_sub:
        sub_end = await user_repo.get_subscription_end(tg_id)
        expire_date = datetime.fromtimestamp(sub_end).strftime('%Y-%m-%d %H:%M')
        sub_text += f"\n\n{t('current_sub_until', expire_date=expire_date)}"
    
    await callback.message.edit_text(sub_text + f"\n\n{t('balance')}: {balance} RUB", reply_markup=sub_kb(t))


@router.callback_query(F.data.in_({"sub_1m", "sub_3m", "sub_6m", "sub_12m"}))
async def sub_buy_callback(callback: CallbackQuery, t):
    data = callback.data
    from config import PLANS
    plan = PLANS[data]
    days = plan["days"]
    price = plan["price"]
    tg_id = callback.from_user.id
    user_repo = UserRepository()
    balance = await user_repo.get_balance(tg_id)
    
    if balance < price:
        await callback.answer(t('low_balance'), show_alert=True)
        return
    
    success = await user_repo.buy_subscription(tg_id, days, price)
    if not success:
        await callback.answer(t('error_buying_sub'), show_alert=True)
        return
    
    has_configs = len(await user_repo.get_configs(tg_id)) > 0
    if has_configs:
        await callback.answer(t('sub_purchased'), show_alert=True)
        configs = await user_repo.get_configs(tg_id)
        has_active_sub = await user_repo.has_active_subscription(tg_id)
        sub_end = await user_repo.get_subscription_end(tg_id)
        expire_date = datetime.fromtimestamp(sub_end).strftime('%Y-%m-%d %H:%M')
        await callback.message.edit_text(
            t('sub_success_with_expire', expire_date=expire_date),
            reply_markup=myvpn_kb(t, configs, has_active_sub)
        )
    else:
        await callback.answer(t('sub_purchased_create_config'), show_alert=True)
        await callback.message.edit_text(t('create_first_config'), reply_markup=myvpn_kb(t, [], True))


@router.callback_query(F.data.startswith("cfg_"))
async def config_selected(callback: CallbackQuery, t):
    cfg_id = int(callback.data.split("_")[1])
    await callback.answer()
    tg_id = callback.from_user.id

    user_repo = UserRepository()
    configs = await user_repo.get_configs(tg_id)
    cfg = next((c for c in configs if c["id"] == cfg_id), None)

    if not cfg:
        text = t('config_not_found')
        await callback.message.edit_text(text, reply_markup=actions_kb(t, cfg_id))
        return

    text = (
        f"{t('your_config')}\n\n"
        f"{t('config_selected')}\n"
        f"<pre><code>{cfg['vless_link']}</code></pre>"
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=actions_kb(t, cfg_id))


@router.callback_query(F.data.startswith("delete_cfg_"))
async def config_delete(callback: CallbackQuery, t):
    cfg_id = int(callback.data.split("_")[2])
    tg_id = callback.from_user.id
    user_repo = UserRepository()
    await user_repo.delete_config(cfg_id, tg_id)
    await callback.answer(t("config_deleted"))
    configs = await user_repo.get_configs(tg_id)
    has_active_sub = await user_repo.has_active_subscription(tg_id)
    text = t("your_configs") if configs else t("no_configs")
    await callback.message.edit_text(text, reply_markup=myvpn_kb(t, configs, has_active_sub))


@router.callback_query(F.data == "renew_subscription")
async def renew_subscription_callback(callback: CallbackQuery, t):
    tg_id = callback.from_user.id
    user_repo = UserRepository()
    balance = await user_repo.get_balance(tg_id)

    await callback.answer()
    await callback.message.edit_text(
        t("extend_subscription") + f"\n\n{t('balance')}: {balance} RUB",
        reply_markup=sub_kb(t)
    )


@router.callback_query(F.data == 'instruction')
async def instruction_callback(callback: CallbackQuery, t):
    await callback.answer()
    text = t("instruction_text")
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=instruction_kb(t))


@router.callback_query(F.data == 'balance')
async def balance_callback(callback: CallbackQuery, t):
    await callback.answer()
    user_repo = UserRepository()
    balance = await user_repo.get_balance(callback.from_user.id)
    await callback.message.edit_text(t('balance_text', balance=balance), reply_markup=balance_kb(t))


@router.callback_query(F.data == 'add_funds')
async def add_funds_callback(callback: CallbackQuery, t):
    await callback.answer()
    await callback.message.edit_text(t('payment_method'), reply_markup=get_payment_methods_keyboard(t))


@router.callback_query(F.data.startswith('pm_'))
async def payment_method_callback(callback: CallbackQuery, t, state: FSMContext):
    method = callback.data.split('_')[1]
    await state.set_state(PaymentState.waiting_amount)
    await state.set_data({'method': method})
    await callback.answer()
    await callback.message.answer(t('enter_amount'))


@router.message(StateFilter(PaymentState.waiting_amount))
async def process_amount(message: Message, state: FSMContext, t):
    try:
        amount = Decimal(message.text)
        if amount < 2:
            raise ValueError
    except (ValueError, Exception):
        await message.answer(t('invalid_amount'))
        return

    data = await state.get_data()
    method = PaymentMethod(data['method'])
    tg_id = message.from_user.id

    try:
        manager = PaymentManager()
        result = await manager.create_payment(
            tg_id=tg_id,
            method=method,
            amount=amount,
            chat_id=message.chat.id if method == PaymentMethod.STARS else None
        )

        # --- TON ---
        if method == PaymentMethod.TON:
            ton_price = await get_ton_price()
            ton_amount = round(float(amount) / ton_price, 2)
            wallet = result.wallet
            comment = result.comment
            text = (
                t(
                    'ton_payment_instruction',
                    ton_amount=f'<b>{ton_amount} TON</b>',
                    wallet=f"<pre><code>{wallet}</code></pre>", 
                    comment=f'<pre>{comment}</pre>'
                )
            )
            await message.answer(text, parse_mode="HTML")

        # --- STARS ---
        elif method == PaymentMethod.STARS and result.url:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить", url=result.url)]
            ])
            await message.answer(result.text, reply_markup=kb)

        await state.clear()

    except Exception as e:
        LOG.exception("Payment creation error")
        await message.answer(t('error_creating_payment'))


@router.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery, bot):
    from config import bot
    if pre_checkout_query.invoice_payload.startswith("topup_"):
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
    else:
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=False,
            error_message="Invalid payload"
        )


@router.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def successful_payment(message: Message, t):
    tg_id = message.from_user.id
    payment_id = message.successful_payment.telegram_payment_charge_id
    stars_paid = message.successful_payment.total_amount
    rub_amount = Decimal(stars_paid) * Decimal(str(TELEGRAM_STARS_RATE))

    payment_repo = PaymentRepository()
    success = await payment_repo.mark_payment_processed(payment_id, tg_id, rub_amount)

    if success:
        user_repo = UserRepository()
        await user_repo.change_balance(tg_id, rub_amount)
        await message.answer(t('payment_success', amount=rub_amount))
    else:
        await message.answer(t('payment_already_processed'))    


@router.callback_query(F.data == 'back_main')
async def back_to_main(callback: CallbackQuery, t):
    await callback.answer()
    await callback.message.edit_text(t('welcome'), reply_markup=main_kb(t))


@router.callback_query(F.data == 'settings')
async def settings_callback(callback: CallbackQuery, t):
    await callback.answer()
    await callback.message.edit_text(t("settings_text"), reply_markup=set_kb(t))


@router.callback_query(F.data == 'change_lang')
async def change_lang_callback(callback: CallbackQuery, t):
    await callback.answer()
    await callback.message.edit_text(t("choose_language"), reply_markup=get_language_keyboard(t))

@router.callback_query(F.data.startswith("set_lang:"))
async def set_lang_callback(callback: CallbackQuery, t):
    lang = callback.data.split(":")[1]
    tg_id = callback.from_user.id
    user_repo = UserRepository()
    await user_repo.set_lang(tg_id, lang)
    await callback.answer(t("language_updated"), show_alert=True)
    new_t = lambda key, **kwargs: t(key=key, lang=lang)
    await callback.message.edit_text(new_t("settings_text"), reply_markup=set_kb(new_t))


@router.callback_query(F.data == 'referral')
async def referral(callback: CallbackQuery, t):
    await callback.answer()
    tg_id = callback.from_user.id
    bot_username = (await callback.message.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{tg_id}"
    text = t('referral_text', ref_link=f"<pre><code>{ref_link}</code></pre>")
    await callback.message.edit_text(text, reply_markup=get_referral_keyboard(t, ref_link), parse_mode="HTML")