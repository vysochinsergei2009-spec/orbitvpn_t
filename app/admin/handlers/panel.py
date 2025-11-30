"""Admin panel handlers - main sections"""

from aiogram import Router, F
from aiogram.types import CallbackQuery

from app.admin.keyboards import admin_panel_kb
from app.core.handlers.utils import safe_answer_callback
from config import ADMIN_TG_ID

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

    from datetime import datetime, timedelta
    from decimal import Decimal
    from sqlalchemy import select, func, case
    from app.repo.db import get_session
    from app.repo.models import User, Payment, Config

    async with get_session() as session:
        now = datetime.utcnow()
        day_ago = now - timedelta(days=1)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        user_stats = select(
            func.count(User.tg_id).label('total_users'),
            func.count(case((User.created_at >= day_ago, 1))).label('new_users_24h'),
            func.count(case((User.created_at >= week_ago, 1))).label('new_users_7d'),
            func.count(case((User.created_at >= month_ago, 1))).label('new_users_30d'),
            func.count(case((User.subscription_end > now, 1))).label('active_subs'),
            func.count(case((User.subscription_end.isnot(None) & (User.subscription_end <= now), 1))).label('expired_subs'),
            func.count(case((User.subscription_end.is_(None), 1))).label('no_subs')
        )

        payment_stats = select(
            func.coalesce(func.sum(case((Payment.status == 'confirmed', Payment.amount))), 0).label('total_revenue'),
            func.coalesce(func.sum(case(((Payment.status == 'confirmed') & (Payment.confirmed_at >= day_ago), Payment.amount))), 0).label('today_revenue'),
            func.coalesce(func.sum(case(((Payment.status == 'confirmed') & (Payment.confirmed_at >= week_ago), Payment.amount))), 0).label('week_revenue'),
            func.coalesce(func.sum(case(((Payment.status == 'confirmed') & (Payment.confirmed_at >= month_ago), Payment.amount))), 0).label('month_revenue')
        )

        config_stats = select(
            func.count(Config.id).label('total_configs'),
            func.count(case((Config.deleted == False, 1))).label('active_configs')
        )

        user_result = (await session.execute(user_stats)).first()
        payment_result = (await session.execute(payment_stats)).first()
        config_result = (await session.execute(config_stats)).first()

        total_users = user_result.total_users or 0
        new_users_24h = user_result.new_users_24h or 0
        new_users_7d = user_result.new_users_7d or 0
        new_users_30d = user_result.new_users_30d or 0
        active_subs = user_result.active_subs or 0
        expired_subs = user_result.expired_subs or 0
        no_subs = user_result.no_subs or 0

        total_revenue = float(payment_result.total_revenue or 0)
        today_revenue = float(payment_result.today_revenue or 0)
        week_revenue = float(payment_result.week_revenue or 0)
        month_revenue = float(payment_result.month_revenue or 0)

        total_configs = config_result.total_configs or 0
        active_configs = config_result.active_configs or 0
        deleted_configs = total_configs - active_configs

    stats_text = t('admin_bot_stats',
                   total_users=total_users,
                   new_users_24h=new_users_24h,
                   new_users_7d=new_users_7d,
                   new_users_30d=new_users_30d,
                   active_subs=active_subs,
                   expired_subs=expired_subs,
                   no_subs=no_subs,
                   total_revenue=total_revenue,
                   today_revenue=today_revenue,
                   week_revenue=week_revenue,
                   month_revenue=month_revenue,
                   total_configs=total_configs,
                   active_configs=active_configs,
                   deleted_configs=deleted_configs)

    await callback.message.edit_text(
        stats_text,
        reply_markup=admin_panel_kb(t)
    )


