from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.filters.state import State, StatesGroup, StateFilter
from aiogram.fsm.context import FSMContext

from app.core.keyboards import set_kb, get_language_keyboard, get_notifications_keyboard
from app.repo.db import get_session
from app.repo.promocode import PromocodeRepository
from .utils import safe_answer_callback, get_repositories

router = Router()


class PromocodeState(StatesGroup):
    waiting_code = State()


@router.callback_query(F.data == 'settings')
async def settings_callback(callback: CallbackQuery, t):
    await safe_answer_callback(callback)
    await callback.message.edit_text(t("settings_text"), reply_markup=set_kb(t))


@router.callback_query(F.data == 'change_lang')
async def change_lang_callback(callback: CallbackQuery, t):
    await safe_answer_callback(callback)
    await callback.message.edit_text(
        t("choose_language"),
        reply_markup=get_language_keyboard(t)
    )


@router.callback_query(F.data.startswith("set_lang:"))
async def set_lang_callback(callback: CallbackQuery, t):
    lang = callback.data.split(":")[1]
    tg_id = callback.from_user.id

    async with get_session() as session:
        user_repo, _ = await get_repositories(session)
        await user_repo.set_lang(tg_id, lang)

    await safe_answer_callback(callback, t("language_updated"), show_alert=True)

    from app.locales.locales import get_translator
    new_t = get_translator(lang)
    await callback.message.edit_text(
        new_t("settings_text"),
        reply_markup=set_kb(new_t)
    )


@router.callback_query(F.data == 'notifications_settings')
async def notifications_settings_callback(callback: CallbackQuery, t):
    tg_id = callback.from_user.id

    async with get_session() as session:
        user_repo, _ = await get_repositories(session)
        notifications_enabled = await user_repo.get_notifications(tg_id)

    status = t('notifications_enabled') if notifications_enabled else t('notifications_disabled')

    await safe_answer_callback(callback)
    await callback.message.edit_text(
        t('notifications_text', status=status),
        reply_markup=get_notifications_keyboard(t)
    )


@router.callback_query(F.data == 'toggle_notifications')
async def toggle_notifications_callback(callback: CallbackQuery, t):
    tg_id = callback.from_user.id

    async with get_session() as session:
        user_repo, _ = await get_repositories(session)
        new_state = await user_repo.toggle_notifications(tg_id)

    status = t('notifications_enabled') if new_state else t('notifications_disabled')

    await safe_answer_callback(callback, t('notifications_updated'), show_alert=True)
    await callback.message.edit_text(
        t('notifications_text', status=status),
        reply_markup=get_notifications_keyboard(t)
    )


@router.callback_query(F.data == 'activate_promocode')
async def activate_promocode_callback(callback: CallbackQuery, t, state: FSMContext):
    """Start promocode activation flow"""
    await safe_answer_callback(callback)

    # Check if user already has an active promocode
    tg_id = callback.from_user.id
    async with get_session() as session:
        promo_repo = PromocodeRepository()
        active_promo = await promo_repo.get_active_promocode_for_user(tg_id)

    if active_promo:
        bonus_text = f"{active_promo.reward_value}% {t('bonus_on_deposit')}"
        await callback.message.edit_text(
            t('promocode_already_active', bonus=bonus_text, code=active_promo.code),
            reply_markup=_get_promocode_back_kb(t)
        )
        return

    await state.set_state(PromocodeState.waiting_code)
    await callback.message.edit_text(
        t('enter_promocode'),
        reply_markup=_get_promocode_back_kb(t)
    )


@router.message(StateFilter(PromocodeState.waiting_code))
async def process_promocode(message: Message, t, state: FSMContext):
    """Process entered promocode"""
    tg_id = message.from_user.id
    code = message.text.strip()

    async with get_session() as session:
        promo_repo = PromocodeRepository()
        success, msg_key, promo = await promo_repo.activate_promocode(tg_id, code)

    await state.clear()

    if success:
        bonus_text = f"{promo.reward_value}% {t('bonus_on_deposit')}"
        text = t('promocode_activated_success', bonus=bonus_text)
    else:
        text = t(msg_key)

    from app.core.keyboards import _build_keyboard
    kb = _build_keyboard([
        {'text': t('back_main'), 'callback_data': 'back_main'},
    ])

    await message.answer(text, reply_markup=kb)


def _get_promocode_back_kb(t):
    """Helper to create back button keyboard"""
    from app.core.keyboards import _build_keyboard
    return _build_keyboard([
        {'text': t('back'), 'callback_data': 'settings'},
    ])
