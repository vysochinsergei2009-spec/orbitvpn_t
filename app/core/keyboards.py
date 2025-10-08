from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_kb(t):
    builder = InlineKeyboardBuilder()
    builder.button(text=t('balance'), callback_data='balance')
    builder.button(text=t('my_vpn'), callback_data='myvpn')
    builder.button(text=t('help'), url='https://t.me/chnddy')
    builder.button(text=t('settings'), callback_data='settings')
    return builder.adjust(2).as_markup()

def balance_kb(t):
    builder = InlineKeyboardBuilder()
    builder.button(text=t('add_funds'), callback_data='add_funds')
    builder.button(text=t('back_main'), callback_data='back_main')
    return builder.adjust(1).as_markup()

def set_kb(t):
    builder = InlineKeyboardBuilder()
    builder.button(text=t('referral'), callback_data='referral')
    builder.button(text=t('change_language'), callback_data='change_lang')
    builder.button(text=t('back_main'), callback_data='back_main')
    return builder.adjust(1).as_markup()

def myvpn_kb(t, configs: list, has_active_sub: bool = False):
    builder = InlineKeyboardBuilder()
    
    if len(configs) == 0:
        if has_active_sub:
            builder.button(text=t("add_config"), callback_data="add_config")
        else:
            builder.button(text=t("buy_sub"), callback_data="buy_sub")

    for cfg in configs:
        builder.button(text=cfg["name"], callback_data=f"cfg_{cfg['id']}")
    if has_active_sub:
        builder.button(text=t("extend"), callback_data="renew_subscription")
    else:
        pass
    
    builder.button(text=t("back_main"), callback_data="back_main")
    return builder.adjust(1).as_markup()


def actions_kb(t, cfg_id: int = None):
    builder = InlineKeyboardBuilder()
    builder.button(text=t("delete_config"), callback_data=f"delete_cfg_{cfg_id}" if cfg_id else "delete_config")
    builder.button(text=t("instruction"), callback_data="instruction")
    builder.button(text=t("back"), callback_data="myvpn")
    return builder.adjust(2).as_markup()

def instruction_kb(t):
    builder = InlineKeyboardBuilder()
    builder.button(text=t("back"), callback_data="myvpn")
    return builder.adjust(1).as_markup()

def get_language_keyboard(t):
    builder = InlineKeyboardBuilder()
    builder.button(text="🇺🇸 English", callback_data="set_lang:en")
    builder.button(text="🇷🇺 Русский", callback_data="set_lang:ru")
    builder.button(text=t("back"), callback_data="settings")
    return builder.adjust(1).as_markup()

def sub_kb(t):
    builder = InlineKeyboardBuilder()
    builder.button(text=t('sub_1m'), callback_data='sub_1m')
    builder.button(text=t('sub_3m'), callback_data='sub_3m')
    builder.button(text=t('sub_6m'), callback_data='sub_6m')
    builder.button(text=t('sub_12m'), callback_data='sub_12m')
    builder.button(text=t('back_main'), callback_data='back_main')
    return builder.adjust(1).as_markup()

def get_payment_methods_keyboard(t):
    builder = InlineKeyboardBuilder()
    builder.button(text='TON', callback_data='pm_ton')
    builder.button(text=t('pm_stars'), callback_data='pm_stars')
    builder.button(text=t('back'), callback_data='balance')
    return builder.adjust(1).as_markup()

def get_referral_keyboard(t, ref_link):
    builder = InlineKeyboardBuilder()
    builder.button(text=t('share'), switch_inline_query=ref_link)
    builder.button(text=t('back'), callback_data='back_main')
    return builder.adjust(1).as_markup()