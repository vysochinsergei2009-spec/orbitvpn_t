from decimal import Decimal
from datetime import datetime

from aiogram import Router, F
from aiogram.filters.state import State, StatesGroup, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery, ContentType, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.exc import OperationalError, TimeoutError as SQLTimeoutError

from app.core.keyboards import (
    balance_kb, get_payment_methods_keyboard, get_payment_amounts_keyboard,
    back_balance, payment_success_actions
)
from app.repo.db import get_session
from app.payments.manager import PaymentManager
from app.payments.models import PaymentMethod
from app.utils.logging import get_logger
from app.utils.redis import get_redis
from config import TELEGRAM_STARS_RATE, PLANS, bot
from .utils import safe_answer_callback, get_repositories, get_user_balance, format_expire_date

router = Router()
LOG = get_logger(__name__)


class PaymentState(StatesGroup):
    waiting_custom_amount = State()


@router.callback_query(F.data == 'balance')
async def balance_callback(callback: CallbackQuery, t, state: FSMContext):
    await safe_answer_callback(callback)
    await state.clear()
    tg_id = callback.from_user.id

    async with get_session() as session:
        user_repo, _ = await get_repositories(session)
        balance = await get_user_balance(user_repo, tg_id)
        has_active_sub = await user_repo.has_active_subscription(tg_id)

        text = t('balance_text', balance=balance)

        if has_active_sub:
            sub_end = await user_repo.get_subscription_end(tg_id)
            expire_date = format_expire_date(sub_end)
            text += f"\n\n{t('subscription_active_until', expire_date=expire_date)}"
        else:
            cheapest = min(PLANS.values(), key=lambda x: x['price'])
            text += f"\n\n{t('subscription_from', price=cheapest['price'])}"

        await callback.message.edit_text(text, reply_markup=balance_kb(t))


@router.callback_query(F.data == 'add_funds')
async def add_funds_callback(callback: CallbackQuery, t):
    await safe_answer_callback(callback)
    await callback.message.edit_text(
        t('payment_method'),
        reply_markup=get_payment_methods_keyboard(t)
    )


@router.callback_query(F.data.startswith('select_method_'))
async def select_payment_method(callback: CallbackQuery, t):
    await safe_answer_callback(callback)
    method = callback.data.replace('select_method_', '')
    await callback.message.edit_text(
        t('select_amount'),
        reply_markup=get_payment_amounts_keyboard(t, method)
    )


@router.callback_query(F.data.startswith('amount_'))
async def process_amount_selection(callback: CallbackQuery, t, state: FSMContext):
    await safe_answer_callback(callback)
    parts = callback.data.split('_')
    method_str = parts[1]
    amount_str = parts[2]

    if amount_str == 'custom':
        await state.set_state(PaymentState.waiting_custom_amount)
        await state.set_data({'method': method_str})
        await callback.message.edit_text(t('enter_amount'), reply_markup=back_balance(t))
        return

    # Validate preset amount
    try:
        amount = Decimal(amount_str)
        # Minimum amount is 200 RUB
        min_amount = 200
        if amount <= 0 or amount < min_amount or amount > 100000:
            raise ValueError("Invalid preset amount")
    except (ValueError, TypeError) as e:
        LOG.error(f"Invalid preset amount: {amount_str} - {e}")
        await callback.message.edit_text(t('invalid_amount'), reply_markup=balance_kb(t))
        return

    await process_payment(callback, t, method_str, amount)


@router.message(StateFilter(PaymentState.waiting_custom_amount))
async def process_custom_amount(message: Message, state: FSMContext, t):
    tg_id = message.from_user.id

    try:
        amount = Decimal(message.text)
        if amount <= 0:
            raise ValueError("Amount must be positive")
        if amount < 200 or amount > 100000:
            raise ValueError("Amount out of range")
        if amount.as_tuple().exponent < -2:
            raise ValueError("Too many decimal places")
    except (ValueError, TypeError) as e:
        LOG.error(f"Invalid amount from user {tg_id}: {message.text} - {e}")
        await message.answer(t('invalid_amount'))
        return

    data = await state.get_data()
    method_str = data.get('method')
    await state.clear()

    await process_payment(message, t, method_str, amount)


async def process_payment(msg_or_callback, t, method_str: str, amount: Decimal):
    tg_id = msg_or_callback.from_user.id
    is_callback = isinstance(msg_or_callback, CallbackQuery)

    try:
        method = PaymentMethod(method_str)
    except ValueError:
        LOG.error(f"Invalid method for user {tg_id}: {method_str}")
        text = t('error_creating_payment')
        if is_callback:
            await msg_or_callback.message.edit_text(text, reply_markup=balance_kb(t))
        else:
            await msg_or_callback.answer(text)
        return

    async with get_session() as session:
        try:
            redis_client = await get_redis()
            manager = PaymentManager(session, redis_client)
            chat_id = msg_or_callback.message.chat.id if is_callback else msg_or_callback.chat.id
            result = await manager.create_payment(t, tg_id=tg_id, method=method, amount=amount, chat_id=chat_id)

            if method == PaymentMethod.TON:
                text = t(
                    'ton_payment_instruction',
                    ton_amount=f'<b>{result.expected_crypto_amount} TON</b>',
                    wallet=f"<pre><code>{result.wallet}</code></pre>",
                    comment=f'<pre>{result.comment}</pre>'
                )
                # Add "Payment Sent" button for TON payments
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=t('payment_sent'), callback_data=f'payment_sent_{result.payment_id}')]
                ])
                if is_callback:
                    await msg_or_callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
                else:
                    await msg_or_callback.answer(text, parse_mode="HTML", reply_markup=kb)

            elif method == PaymentMethod.STARS and result.url:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=t('pay_button'), url=result.url)]
                ])
                if is_callback:
                    await msg_or_callback.message.edit_text(result.text, reply_markup=kb)
                else:
                    await msg_or_callback.answer(result.text, reply_markup=kb)

            elif method == PaymentMethod.CRYPTOBOT and result.pay_url:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=t('pay_button'), url=result.pay_url)]
                ])
                if is_callback:
                    await msg_or_callback.message.edit_text(result.text, reply_markup=kb)
                else:
                    await msg_or_callback.answer(result.text, reply_markup=kb)

            elif method == PaymentMethod.YOOKASSA and result.pay_url:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=t('pay_button'), url=result.pay_url)],
                    [InlineKeyboardButton(text=t('payment_sent'), callback_data=f'payment_sent_{result.payment_id}')]
                ])
                if is_callback:
                    await msg_or_callback.message.edit_text(result.text, reply_markup=kb)
                else:
                    await msg_or_callback.answer(result.text, reply_markup=kb)

        except ValueError as e:
            error_msg = str(e)
            # Check if it's an active payment error
            if error_msg.startswith("active_payment:"):
                parts = error_msg.split(":")
                active_payment_id = int(parts[1])
                active_amount = parts[2]
                active_method = parts[3]

                # Show choice to user: continue with existing or create new
                text = t('active_payment_exists', amount=active_amount, method=active_method.upper())
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=t('continue_payment'), callback_data=f'continue_payment_{active_payment_id}')],
                    [InlineKeyboardButton(text=t('create_new_payment'), callback_data=f'force_payment_{method_str}_{amount}')],
                    [InlineKeyboardButton(text=t('back'), callback_data='balance')]
                ])
                if is_callback:
                    await msg_or_callback.message.edit_text(text, reply_markup=kb)
                else:
                    await msg_or_callback.answer(text, reply_markup=kb)
            else:
                LOG.error(f"Payment error for user {tg_id}: ValueError: {e}")
                text = t('error_creating_payment')
                if is_callback:
                    await msg_or_callback.message.edit_text(text, reply_markup=balance_kb(t))
                else:
                    await msg_or_callback.answer(text)
        except (OperationalError, SQLTimeoutError) as e:
            LOG.error(f"Database error for user {tg_id}: {type(e).__name__}: {e}")
            text = t('service_temporarily_unavailable')
            if is_callback:
                await msg_or_callback.message.edit_text(text, reply_markup=balance_kb(t))
            else:
                await msg_or_callback.answer(text)
        except Exception as e:
            LOG.error(f"Payment error for user {tg_id}: {type(e).__name__}: {e}")
            text = t('error_creating_payment')
            if is_callback:
                await msg_or_callback.message.edit_text(text, reply_markup=balance_kb(t))
            else:
                await msg_or_callback.answer(text)


@router.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    payload = pre_checkout_query.invoice_payload

    if not payload.startswith("topup_"):
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=False,
            error_message="Invalid payment format"
        )
        return

    try:
        parts = payload.split("_")
        if len(parts) != 3:
            raise ValueError("Invalid payload structure")
        tg_id = int(parts[1])
        amount = int(parts[2])

        if tg_id != pre_checkout_query.from_user.id:
            LOG.warning(f"User {pre_checkout_query.from_user.id} tried to pay for user {tg_id}")
            await bot.answer_pre_checkout_query(
                pre_checkout_query.id,
                ok=False,
                error_message="Invalid payment recipient"
            )
            return

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

    if not message.successful_payment:
        LOG.error(f"Successful payment message without payment data for user {tg_id}")
        return

    payment_id = message.successful_payment.telegram_payment_charge_id
    stars_paid = message.successful_payment.total_amount

    if not payment_id or not stars_paid:
        LOG.error(f"Invalid payment data for user {tg_id}: payment_id={payment_id}, stars={stars_paid}")
        await message.answer(t('error_creating_payment'))
        return

    rub_amount = Decimal(stars_paid) * Decimal(str(TELEGRAM_STARS_RATE))

    async with get_session() as session:
        try:
            from app.repo.models import Payment as PaymentModel, User
            from sqlalchemy import select

            # CRITICAL FIX: Acquire database lock FIRST to prevent race conditions
            # Lock user row to serialize all payment confirmations for this user
            result = await session.execute(
                select(User).where(User.tg_id == tg_id).with_for_update()
            )
            user = result.scalar_one_or_none()
            if not user:
                LOG.error(f"User {tg_id} not found for Stars payment")
                await message.answer(t('user_not_found'))
                return

            # Find pending Stars payment with lock
            result = await session.execute(
                select(PaymentModel).where(
                    PaymentModel.tg_id == tg_id,
                    PaymentModel.method == 'stars',
                    PaymentModel.status == 'pending',
                    PaymentModel.amount == rub_amount
                ).with_for_update()
            )
            payment = result.scalar_one_or_none()

            if not payment:
                # Check if already confirmed with this tx_hash (duplicate webhook)
                result = await session.execute(
                    select(PaymentModel).where(
                        PaymentModel.tx_hash == payment_id,
                        PaymentModel.status == 'confirmed'
                    )
                )
                existing = result.scalar_one_or_none()
                if existing:
                    LOG.warning(f"Stars payment {payment_id} already confirmed (duplicate webhook)")
                    await message.answer(t('payment_already_processed'))
                    return

                LOG.error(f"No pending Stars payment found for user {tg_id} with amount {rub_amount}")
                await message.answer(t('payment_not_found'))
                return

            # Check if payment expired
            if payment.expires_at and datetime.utcnow() > payment.expires_at:
                LOG.warning(f"Stars payment {payment.id} expired (expires_at: {payment.expires_at})")
                payment.status = 'expired'
                await session.commit()
                await message.answer(t('payment_expired'))
                return

            # Check if tx_hash already used (should be caught by unique constraint, but double-check)
            if payment.tx_hash is not None:
                LOG.warning(f"Payment {payment.id} already has tx_hash: {payment.tx_hash}")
                await message.answer(t('payment_already_processed'))
                return

            # Store old balance for logging
            old_balance = user.balance

            # ATOMIC UPDATE: Update payment status and balance in single transaction
            payment.status = 'confirmed'
            payment.tx_hash = payment_id
            payment.confirmed_at = datetime.utcnow()

            user.balance += rub_amount
            new_balance = user.balance

            # Commit transaction atomically
            await session.commit()

            LOG.info(f"Stars payment confirmed: payment_id={payment.id}, user={tg_id}, "
                    f"amount={rub_amount}, balance: {old_balance} → {new_balance}, tx_hash={payment_id}")

            # Invalidate cache after successful commit (tolerate Redis failures)
            try:
                user_repo, _ = await get_repositories(session)
                redis = await user_repo.get_redis()
                await redis.delete(f"user:{tg_id}:balance")
            except Exception as redis_err:
                LOG.warning(f"Redis error invalidating cache for user {tg_id}: {redis_err}")
                # Don't fail payment confirmation - balance was updated successfully

            has_active_sub = await user_repo.has_active_subscription(tg_id)

            await message.answer(
                t('payment_success', amount=float(rub_amount)),
                reply_markup=payment_success_actions(t, has_active_sub)
            )

        except Exception as e:
            await session.rollback()
            LOG.error(f"Error confirming Stars payment for user {tg_id}: {type(e).__name__}: {e}")
            await message.answer(t('error_creating_payment'))
            raise


@router.callback_query(F.data.startswith('continue_payment_'))
async def continue_payment_callback(callback: CallbackQuery, t):
    """Continue with existing payment"""
    await safe_answer_callback(callback)

    try:
        payment_id = int(callback.data.replace('continue_payment_', ''))

        async with get_session() as session:
            _, payment_repo = await get_repositories(session)
            payment = await payment_repo.get_payment(payment_id)

            if not payment or payment['status'] != 'pending':
                await callback.message.edit_text(
                    t('payment_expired'),
                    reply_markup=balance_kb(t)
                )
                return

            # Recreate payment message with the existing payment
            method = PaymentMethod(payment['method'])

            if method == PaymentMethod.TON:
                text = t(
                    'ton_payment_instruction',
                    ton_amount=f'<b>{payment["expected_crypto_amount"]} TON</b>',
                    wallet=f"<pre><code>{payment.get("wallet", "N/A")}</code></pre>",
                    comment=f'<pre>{payment["comment"]}</pre>'
                )
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=t('payment_sent'), callback_data=f'payment_sent_{payment_id}')]
                ])
                await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

            elif method == PaymentMethod.CRYPTOBOT:
                extra_data = payment.get('extra_data', {})
                invoice_id = extra_data.get('invoice_id') if extra_data else None

                if invoice_id:
                    # Reconstruct pay URL
                    from config import CRYPTOBOT_TESTNET
                    domain = "testnet-pay.crypt.bot" if CRYPTOBOT_TESTNET else "pay.crypt.bot"
                    pay_url = f"https://{domain}/invoice/{invoice_id}"

                    text = (
                        t("cryptobot_payment_intro") + "\n\n"
                        + t("cryptobot_amount", amount=payment['amount']) + "\n\n"
                        + t("cryptobot_click_button")
                    )
                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=t('pay_button'), url=pay_url)]
                    ])
                    await callback.message.edit_text(text, reply_markup=kb)
                else:
                    await callback.message.edit_text(t('error_creating_payment'), reply_markup=balance_kb(t))

            elif method == PaymentMethod.YOOKASSA:
                extra_data = payment.get('extra_data', {})
                yookassa_payment_id = extra_data.get('yookassa_payment_id') if extra_data else None

                if yookassa_payment_id:
                    # Reconstruct payment URL from YooKassa
                    # Note: We need to fetch the payment URL from YooKassa API
                    from yookassa import Payment as YooKassaPayment
                    from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY
                    from yookassa import Configuration

                    Configuration.configure(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)
                    yookassa_payment = YooKassaPayment.find_one(yookassa_payment_id)

                    if yookassa_payment and yookassa_payment.confirmation:
                        pay_url = yookassa_payment.confirmation.confirmation_url
                        text = (
                            t("yookassa_payment_intro") + "\n\n"
                            + t("yookassa_amount", amount=payment['amount']) + "\n\n"
                            + t("yookassa_click_button")
                        )
                        kb = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text=t('pay_button'), url=pay_url)],
                            [InlineKeyboardButton(text=t('payment_sent'), callback_data=f'payment_sent_{payment_id}')]
                        ])
                        await callback.message.edit_text(text, reply_markup=kb)
                    else:
                        await callback.message.edit_text(t('error_creating_payment'), reply_markup=balance_kb(t))
                else:
                    await callback.message.edit_text(t('error_creating_payment'), reply_markup=balance_kb(t))

            else:
                await callback.message.edit_text(t('error_creating_payment'), reply_markup=balance_kb(t))

    except Exception as e:
        LOG.error(f"Error continuing payment: {e}")
        await callback.message.edit_text(
            t('error_creating_payment'),
            reply_markup=balance_kb(t)
        )


@router.callback_query(F.data.startswith('force_payment_'))
async def force_payment_callback(callback: CallbackQuery, t):
    """Create new payment even if active one exists"""
    await safe_answer_callback(callback)

    try:
        parts = callback.data.replace('force_payment_', '').split('_')
        method_str = parts[0]
        amount = Decimal(parts[1])

        tg_id = callback.from_user.id

        async with get_session() as session:
            redis_client = await get_redis()
            manager = PaymentManager(session, redis_client)
            method = PaymentMethod(method_str)

            # Create payment with force_new=True
            result = await manager.create_payment(
                t,
                tg_id=tg_id,
                method=method,
                amount=amount,
                chat_id=callback.message.chat.id,
                force_new=True
            )

            # Display payment details
            if method == PaymentMethod.TON:
                text = t(
                    'ton_payment_instruction',
                    ton_amount=f'<b>{result.expected_crypto_amount} TON</b>',
                    wallet=f"<pre><code>{result.wallet}</code></pre>",
                    comment=f'<pre>{result.comment}</pre>'
                )
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=t('payment_sent'), callback_data=f'payment_sent_{result.payment_id}')]
                ])
                await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

            elif method == PaymentMethod.STARS and result.url:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=t('pay_button'), url=result.url)]
                ])
                await callback.message.edit_text(result.text, reply_markup=kb)

            elif method == PaymentMethod.CRYPTOBOT and result.pay_url:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=t('pay_button'), url=result.pay_url)]
                ])
                await callback.message.edit_text(result.text, reply_markup=kb)

            elif method == PaymentMethod.YOOKASSA and result.pay_url:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=t('pay_button'), url=result.pay_url)],
                    [InlineKeyboardButton(text=t('payment_sent'), callback_data=f'payment_sent_{result.payment_id}')]
                ])
                await callback.message.edit_text(result.text, reply_markup=kb)

    except Exception as e:
        LOG.error(f"Error creating forced payment: {e}")
        await callback.message.edit_text(
            t('error_creating_payment'),
            reply_markup=balance_kb(t)
        )


@router.callback_query(F.data.startswith('payment_sent_'))
async def payment_sent_callback(callback: CallbackQuery, t):
    """Handle 'Payment Sent' button - check payment immediately"""
    await safe_answer_callback(callback, t('payment_checking'), show_alert=True)

    tg_id = callback.from_user.id
    payment_id = int(callback.data.replace('payment_sent_', ''))

    async with get_session() as session:
        try:
            redis_client = await get_redis()
            manager = PaymentManager(session, redis_client)

            # Get payment details first
            _, payment_repo = await get_repositories(session)
            payment = await payment_repo.get_payment(payment_id)

            if not payment:
                raise ValueError(f"Payment {payment_id} not found")

            # Check payment immediately when user clicks button
            confirmed = await manager.check_payment(payment_id)

            # Get updated balance
            user_repo, _ = await get_repositories(session)
            balance = await get_user_balance(user_repo, tg_id)
            has_active_sub = await user_repo.has_active_subscription(tg_id)

            if confirmed:
                # Payment confirmed successfully
                text = t('payment_success', amount=float(payment['amount'])) + "\n\n" + t('balance_text', balance=balance)
            else:
                # Payment not yet confirmed
                text = t('payment_not_found') + "\n\n" + t('balance_text', balance=balance)

            if has_active_sub:
                from .utils import format_expire_date
                sub_end = await user_repo.get_subscription_end(tg_id)
                expire_date = format_expire_date(sub_end)
                text += f"\n\n{t('subscription_active_until', expire_date=expire_date)}"
            else:
                from config import PLANS
                cheapest = min(PLANS.values(), key=lambda x: x['price'])
                text += f"\n\n{t('subscription_from', price=cheapest['price'])}"

            await callback.message.edit_text(text, reply_markup=balance_kb(t))

        except Exception as e:
            LOG.error(f"Error checking payment {payment_id}: {e}")
            # Fallback to showing balance screen
            user_repo, _ = await get_repositories(session)
            balance = await get_user_balance(user_repo, tg_id)
            text = t('balance_text', balance=balance)
            await callback.message.edit_text(text, reply_markup=balance_kb(t))
