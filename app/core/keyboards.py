from collections.abc import Callable
from typing import Any

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import PLANS


def _build_keyboard(
    buttons: list[dict[str, Any]],
    adjust: int | list[int] = 1,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for btn in buttons:
        if 'url' in btn:
            builder.button(text=btn['text'], url=btn['url'])
        elif 'switch_inline_query' in btn:
            builder.button(text=btn['text'], switch_inline_query=btn['switch_inline_query'])
        else:
            builder.button(text=btn['text'], callback_data=btn['callback_data'])

    if isinstance(adjust, int):
        return builder.adjust(adjust).as_markup()
    else:
        return builder.adjust(*adjust).as_markup()


def main_kb(t: Callable[[str], str]) -> InlineKeyboardMarkup:
    return _build_keyboard([
        {'text': t('balance'), 'callback_data': 'balance'},
        {'text': t('my_vpn'), 'callback_data': 'myvpn'},
        {'text': t('help'), 'url': 'https://t.me/chnddy'},
        {'text': t('settings'), 'callback_data': 'settings'},
    ], adjust=2)


def balance_kb(t: Callable[[str], str]) -> InlineKeyboardMarkup:
    return _build_keyboard([
        {'text': t('add_funds'), 'callback_data': 'add_funds'},
        {'text': t('back_main'), 'callback_data': 'back_main'},
    ])


def set_kb(t: Callable[[str], str]) -> InlineKeyboardMarkup:
    return _build_keyboard([
        {'text': t('referral'), 'callback_data': 'referral'},
        {'text': t('change_language'), 'callback_data': 'change_lang'},
        {'text': t('back_main'), 'callback_data': 'back_main'},
    ])


def myvpn_kb(
    t: Callable[[str], str],
    configs: list[dict[str, Any]],
    has_active_sub: bool = False,
) -> InlineKeyboardMarkup:
    buttons = []

    if not configs:
        buttons.append({
            'text': t('add_config' if has_active_sub else 'buy_sub'),
            'callback_data': 'add_config' if has_active_sub else 'buy_sub',
        })

    buttons.extend(
        {'text': cfg['name'], 'callback_data': f"cfg_{cfg['id']}"}
        for cfg in configs
    )

    if has_active_sub:
        buttons.append({'text': t('extend'), 'callback_data': 'renew_subscription'})

    buttons.append({'text': t('back_main'), 'callback_data': 'back_main'})

    return _build_keyboard(buttons)


def actions_kb(t: Callable[[str], str], cfg_id: int | None = None) -> InlineKeyboardMarkup:
    delete_callback = f"delete_cfg_{cfg_id}" if cfg_id else "delete_config"

    return _build_keyboard([
        {'text': t('delete_config'), 'callback_data': delete_callback},
        {'text': t('instruction'), 'callback_data': 'instruction'},
        {'text': t('back'), 'callback_data': 'myvpn'},
    ], adjust=2)


def instruction_kb(t: Callable[[str], str]) -> InlineKeyboardMarkup:
    return _build_keyboard([
        {'text': t('back'), 'callback_data': 'myvpn'},
    ])


def get_language_keyboard(t: Callable[[str], str]) -> InlineKeyboardMarkup:
    return _build_keyboard([
        {'text': '🇺🇸 English', 'callback_data': 'set_lang:en'},
        {'text': '🇷🇺 Русский', 'callback_data': 'set_lang:ru'},
        {'text': t('back'), 'callback_data': 'settings'},
    ])


def sub_kb(t: Callable[[str], str]) -> InlineKeyboardMarkup:
    buttons = [
        {'text': t(key).format(price=plan['price']), 'callback_data': key}
        for key, plan in PLANS.items()
        if key.startswith('sub_')
    ]

    buttons.append({'text': t('back_main'), 'callback_data': 'back_main'})

    return _build_keyboard(buttons)


def get_payment_methods_keyboard(t: Callable[[str], str]) -> InlineKeyboardMarkup:
    return _build_keyboard([
        {'text': 'TON', 'callback_data': 'pm_ton'},
        {'text': t('pm_stars'), 'callback_data': 'pm_stars'},
        {'text': t('back'), 'callback_data': 'balance'},
    ])


def get_referral_keyboard(t: Callable[[str], str], ref_link: str) -> InlineKeyboardMarkup:
    return _build_keyboard([
        {'text': t('share'), 'switch_inline_query': ref_link},
        {'text': t('back'), 'callback_data': 'back_main'},
    ])


def back_balance(t: Callable[[str], str]) -> InlineKeyboardMarkup:
    return _build_keyboard([
        {'text': t('back'), 'callback_data': 'balance'},
    ])
