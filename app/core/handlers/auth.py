from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery

from app.core.keyboards import main_kb, get_referral_keyboard
from app.repo.db import get_session
from config import FREE_TRIAL_DAYS
from .utils import safe_answer_callback, get_repositories, extract_referrer_id

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, t):
    tg_id = message.from_user.id
    username = message.from_user.username or f"unknown_{tg_id}"
    referrer_id = extract_referrer_id(message.text)

    # Prevent self-referral
    if referrer_id and referrer_id == tg_id:
        referrer_id = None

    async with get_session() as session:
        user_repo, _ = await get_repositories(session)

        is_new_user = await user_repo.add_if_not_exists(tg_id, username, referrer_id=referrer_id)
        if is_new_user:
            await user_repo.buy_subscription(tg_id, days=FREE_TRIAL_DAYS, price=0.0)

        await message.answer(t("cmd_start"), reply_markup=main_kb(t, user_id=tg_id))

        if is_new_user:
            await message.answer(t("free_trial_activated"))


@router.callback_query(F.data == 'back_main')
async def back_to_main(callback: CallbackQuery, t):
    await safe_answer_callback(callback)
    tg_id = callback.from_user.id
    await callback.message.edit_text(t('welcome'), reply_markup=main_kb(t, user_id=tg_id))


@router.callback_query(F.data == 'referral')
async def referral(callback: CallbackQuery, t):
    await safe_answer_callback(callback)
    tg_id = callback.from_user.id

    bot_username = (await callback.message.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{tg_id}"

    text = t('referral_text', ref_link=f"<pre><code>{ref_link}</code></pre>")
    await callback.message.edit_text(
        text,
        reply_markup=get_referral_keyboard(t, ref_link),
        parse_mode="HTML"
    )
