from io import BytesIO

from aiogram import Router, F
from aiogram.types import CallbackQuery, LinkPreviewOptions, BufferedInputFile
from sqlalchemy.exc import OperationalError, TimeoutError as SQLTimeoutError
import qrcode

from app.core.keyboards import actions_kb, sub_kb, qr_delete_kb
from app.repo.db import get_session
from app.utils.logging import get_logger
from config import INSTALL_GUIDE_URLS
from .utils import safe_answer_callback, get_repositories, update_configs_view

router = Router()
LOG = get_logger(__name__)


@router.callback_query(F.data == "myvpn")
async def myvpn_callback(callback: CallbackQuery, t):
    await safe_answer_callback(callback)

    async with get_session() as session:
        user_repo, _ = await get_repositories(session)
        await update_configs_view(callback, t, user_repo, callback.from_user.id)


@router.callback_query(F.data == "add_config")
async def add_config_callback(callback: CallbackQuery, t):
    tg_id = callback.from_user.id

    async with get_session() as session:
        user_repo, _ = await get_repositories(session)

        await safe_answer_callback(callback, t('creating_config'))

        try:
            await user_repo.create_and_add_config(tg_id)
            await update_configs_view(callback, t, user_repo, tg_id, t('config_created'))

        except ValueError as e:
            error_msg = str(e)
            if "No active subscription" in error_msg or "Subscription expired" in error_msg:
                await callback.message.edit_text(t('subscription_expired'), reply_markup=sub_kb(t))
            elif "Max configs reached" in error_msg:
                await safe_answer_callback(callback, t('max_configs_reached'), show_alert=True)
            elif "No active Marzban instances" in error_msg:
                await safe_answer_callback(callback, t('no_servers_or_cache_error'), show_alert=True)
            else:
                LOG.error(f"ValueError creating config for user {tg_id}: {error_msg}")
                await safe_answer_callback(callback, t('error_creating_config'), show_alert=True)

        except (OperationalError, SQLTimeoutError) as e:
            LOG.error(f"Database error creating config for user {tg_id}: {type(e).__name__}: {e}")
            await safe_answer_callback(callback, t('service_temporarily_unavailable'), show_alert=True)

        except Exception as e:
            LOG.error(f"Unexpected error creating config for user {tg_id}: {type(e).__name__}: {e}")
            await safe_answer_callback(callback, t('error_creating_config'), show_alert=True)


@router.callback_query(F.data.startswith("cfg_"))
async def config_selected(callback: CallbackQuery, t, lang: str):
    await safe_answer_callback(callback)
    cfg_id = int(callback.data.split("_")[1])
    tg_id = callback.from_user.id

    async with get_session() as session:
        user_repo, _ = await get_repositories(session)
        configs = await user_repo.get_configs(tg_id)

        cfg = next((c for c in configs if c["id"] == cfg_id), None)
        if not cfg:
            await callback.message.edit_text(t('config_not_found'), reply_markup=actions_kb(t, cfg_id))
            return

        install_url = INSTALL_GUIDE_URLS.get(lang, INSTALL_GUIDE_URLS["ru"])

        text = f"{t('your_config')}\n\n{t('config_selected')}\n<pre><code>{cfg['vless_link']}</code></pre>\n<a href='{install_url}'>{t('how_to_install')}</a>"
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=actions_kb(t, cfg_id),
            link_preview_options=LinkPreviewOptions(is_disabled=True)
        )


@router.callback_query(F.data.startswith("delete_cfg_"))
async def config_delete(callback: CallbackQuery, t):
    cfg_id = int(callback.data.split("_")[2])
    tg_id = callback.from_user.id

    async with get_session() as session:
        user_repo, _ = await get_repositories(session)

        try:
            await user_repo.delete_config(cfg_id, tg_id)
            await safe_answer_callback(callback, t("config_deleted"))
            await update_configs_view(callback, t, user_repo, tg_id)

        except Exception as e:
            LOG.error(f"Error deleting config {cfg_id} for user {tg_id}: {type(e).__name__}: {e}")
            await safe_answer_callback(callback, t('error_deleting_config'), show_alert=True)


@router.callback_query(F.data.startswith("qr_cfg_"))
async def qr_config(callback: CallbackQuery, t):
    await safe_answer_callback(callback)
    cfg_id = int(callback.data.split("_")[2])
    tg_id = callback.from_user.id

    async with get_session() as session:
        user_repo, _ = await get_repositories(session)
        configs = await user_repo.get_configs(tg_id)

        cfg = next((c for c in configs if c["id"] == cfg_id), None)
        if not cfg:
            await safe_answer_callback(callback, t('config_not_found'), show_alert=True)
            return

        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(cfg['vless_link'])
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")

            bio = BytesIO()
            img.save(bio, format='PNG')
            bio.seek(0)

            photo = BufferedInputFile(bio.read(), filename="qr_code.png")
            await callback.message.answer_photo(
                photo=photo,
                caption=t('your_config'),
                reply_markup=qr_delete_kb(t)
            )

        except Exception as e:
            LOG.error(f"Error generating QR code for config {cfg_id}: {type(e).__name__}: {e}")
            await safe_answer_callback(callback, t('error_creating_config'), show_alert=True)


@router.callback_query(F.data == "delete_qr_msg")
async def delete_qr_message(callback: CallbackQuery):
    await safe_answer_callback(callback)
    await callback.message.delete()
