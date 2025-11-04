from collections.abc import Callable
from typing import Any

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_TG_ID, PLANS


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


def qr_delete_kb(t: Callable[[str], str]) -> InlineKeyboardMarkup:
    return _build_keyboard([
        {'text': t('delete_config'), 'callback_data': 'delete_qr_msg'},
    ])


def main_kb(t: Callable[[str], str], user_id: int | None = None) -> InlineKeyboardMarkup:
    buttons = [
        {'text': t('my_vpn'), 'callback_data': 'myvpn'},
        {'text': t('balance'), 'callback_data': 'balance'},
        {'text': t('settings'), 'callback_data': 'settings'},
    ]

    # Show Admin button for admin, Help for others
    if user_id and user_id == ADMIN_TG_ID:
        buttons.append({'text': t('admin'), 'callback_data': 'admin_panel'})
    else:
        buttons.append({'text': t('help'), 'url': 'https://t.me/chnddy'})

    return _build_keyboard(buttons, adjust=[1, 1, 2])


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

    for i, cfg in enumerate(configs, 1):

        display_name = cfg.get('name') or f"{t('config')} {i}"
        buttons.append({
            'text': display_name,
            'callback_data': f"cfg_{cfg['id']}"
        })

    if has_active_sub:
        buttons.append({'text': t('extend'), 'callback_data': 'renew_subscription'})

    buttons.append({'text': t('back_main'), 'callback_data': 'back_main'})

    return _build_keyboard(buttons)


def actions_kb(t: Callable[[str], str], cfg_id: int | None = None) -> InlineKeyboardMarkup:
    delete_callback = f"delete_cfg_{cfg_id}" if cfg_id else "delete_config"
    qr_callback = f"qr_cfg_{cfg_id}" if cfg_id else "qr_config"

    return _build_keyboard([
        {'text': t('delete_config'), 'callback_data': delete_callback},
        {'text': t('qr_code'), 'callback_data': qr_callback},
        {'text': t('back'), 'callback_data': 'myvpn'},
    ], adjust=2)


def get_language_keyboard(t: Callable[[str], str]) -> InlineKeyboardMarkup:
    return _build_keyboard([
        {'text': '🇺🇸 English', 'callback_data': 'set_lang:en'},
        {'text': '🇷🇺 Русский', 'callback_data': 'set_lang:ru'},
        {'text': t('back'), 'callback_data': 'settings'},
    ])


def sub_kb(t: Callable[[str], str], is_extension: bool = False) -> InlineKeyboardMarkup:
    if is_extension:
        buttons = [
            {'text': t(f'extend_by_{key.split("_")[1]}').format(price=plan['price']), 'callback_data': key}
            for key, plan in PLANS.items()
            if key.startswith('sub_')
        ]
    else:
        buttons = [
            {'text': t(key).format(price=plan['price']), 'callback_data': key}
            for key, plan in PLANS.items()
            if key.startswith('sub_')
        ]

    buttons.append({'text': t('back_main'), 'callback_data': 'back_main'})

    return _build_keyboard(buttons)


def get_payment_methods_keyboard(t: Callable[[str], str]) -> InlineKeyboardMarkup:
    return _build_keyboard([
        {'text': 'TON', 'callback_data': 'select_method_ton'},
        {'text': t('pm_stars'), 'callback_data': 'select_method_stars'},
        {'text': 'CryptoBot (USDT)', 'callback_data': 'select_method_cryptobot'},
        {'text': 'YooKassa (RUB)', 'callback_data': 'select_method_yookassa'},
        {'text': t('back'), 'callback_data': 'balance'},
    ], adjust=1)


def get_referral_keyboard(t: Callable[[str], str], ref_link: str) -> InlineKeyboardMarkup:
    return _build_keyboard([
        {'text': t('share'), 'switch_inline_query': ref_link},
        {'text': t('back'), 'callback_data': 'back_main'},
    ])


def back_balance(t: Callable[[str], str]) -> InlineKeyboardMarkup:
    return _build_keyboard([
        {'text': t('back'), 'callback_data': 'balance'},
    ])


def get_payment_amounts_keyboard(t: Callable[[str], str], method: str) -> InlineKeyboardMarkup:
    # All methods support custom amounts
    return _build_keyboard([
        {'text': '200 RUB', 'callback_data': f'amount_{method}_200'},
        {'text': '500 RUB', 'callback_data': f'amount_{method}_500'},
        {'text': '1000 RUB', 'callback_data': f'amount_{method}_1000'},
        {'text': t('custom_amount'), 'callback_data': f'amount_{method}_custom'},
        {'text': t('back'), 'callback_data': 'add_funds'},
    ], adjust=[3, 1, 1])


def payment_success_actions(t: Callable[[str], str], has_active_sub: bool) -> InlineKeyboardMarkup:
    """Next action buttons after successful payment"""
    if has_active_sub:
        return _build_keyboard([
            {'text': t('extend'), 'callback_data': 'renew_subscription'},
            {'text': t('back_main'), 'callback_data': 'back_main'},
        ])
    else:
        return _build_keyboard([
            {'text': t('buy_sub'), 'callback_data': 'buy_sub'},
            {'text': t('back_main'), 'callback_data': 'back_main'},
        ])


def admin_panel_kb(t: Callable[[str], str]) -> InlineKeyboardMarkup:
    """Admin panel keyboard with various management options"""
    return _build_keyboard([
        {'text': t('admin_stats'), 'callback_data': 'admin_stats'},
        {'text': t('admin_users'), 'callback_data': 'admin_users'},
        {'text': t('admin_payments'), 'callback_data': 'admin_payments'},
        {'text': t('admin_servers'), 'callback_data': 'admin_servers'},
        {'text': t('admin_broadcast'), 'callback_data': 'admin_broadcast'},
        {'text': t('back_main'), 'callback_data': 'back_main'},
    ], adjust=[2, 2, 1, 1])
