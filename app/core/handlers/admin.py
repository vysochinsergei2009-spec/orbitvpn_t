from aiogram import Router, F
from aiogram.types import CallbackQuery

from app.core.keyboards import admin_panel_kb
from config import ADMIN_TG_ID
from .utils import safe_answer_callback

router = Router()


@router.callback_query(F.data == 'admin_panel')
async def show_admin_panel(callback: CallbackQuery, t):
    """Show admin panel - only accessible to admin"""
    await safe_answer_callback(callback)
    tg_id = callback.from_user.id

    # Security check: only admin can access
    if tg_id != ADMIN_TG_ID:
        await callback.answer(t('access_denied'), show_alert=True)
        return

    await callback.message.edit_text(
        t('admin_panel_welcome'),
        reply_markup=admin_panel_kb(t)
    )


@router.callback_query(F.data == 'admin_stats')
async def admin_stats(callback: CallbackQuery, t):
    """Show bot statistics"""
    await safe_answer_callback(callback)
    tg_id = callback.from_user.id

    if tg_id != ADMIN_TG_ID:
        await callback.answer(t('access_denied'), show_alert=True)
        return

    # TODO: Implement actual statistics
    stats_text = t('admin_stats_placeholder')

    await callback.message.edit_text(
        stats_text,
        reply_markup=admin_panel_kb(t)
    )


@router.callback_query(F.data == 'admin_users')
async def admin_users(callback: CallbackQuery, t):
    """Show user management"""
    await safe_answer_callback(callback)
    tg_id = callback.from_user.id

    if tg_id != ADMIN_TG_ID:
        await callback.answer(t('access_denied'), show_alert=True)
        return

    # TODO: Implement user management
    users_text = t('admin_users_placeholder')

    await callback.message.edit_text(
        users_text,
        reply_markup=admin_panel_kb(t)
    )


@router.callback_query(F.data == 'admin_payments')
async def admin_payments(callback: CallbackQuery, t):
    """Show payment statistics"""
    await safe_answer_callback(callback)
    tg_id = callback.from_user.id

    if tg_id != ADMIN_TG_ID:
        await callback.answer(t('access_denied'), show_alert=True)
        return

    # TODO: Implement payment statistics
    payments_text = t('admin_payments_placeholder')

    await callback.message.edit_text(
        payments_text,
        reply_markup=admin_panel_kb(t)
    )


@router.callback_query(F.data == 'admin_servers')
async def admin_servers(callback: CallbackQuery, t):
    """Show server status"""
    await safe_answer_callback(callback)
    tg_id = callback.from_user.id

    if tg_id != ADMIN_TG_ID:
        await callback.answer(t('access_denied'), show_alert=True)
        return

    # TODO: Implement server status
    servers_text = t('admin_servers_placeholder')

    await callback.message.edit_text(
        servers_text,
        reply_markup=admin_panel_kb(t)
    )


@router.callback_query(F.data == 'admin_broadcast')
async def admin_broadcast(callback: CallbackQuery, t):
    """Broadcast message to all users"""
    await safe_answer_callback(callback)
    tg_id = callback.from_user.id

    if tg_id != ADMIN_TG_ID:
        await callback.answer(t('access_denied'), show_alert=True)
        return

    # TODO: Implement broadcast functionality
    broadcast_text = t('admin_broadcast_placeholder')

    await callback.message.edit_text(
        broadcast_text,
        reply_markup=admin_panel_kb(t)
    )
