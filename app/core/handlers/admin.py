"""
Admin commands for promocode management.

Commands:
    /create_promo CODE PERCENT [LIMIT] [DAYS] - Create promocode
    /list_promos - List all promocodes
    /deactivate_promo CODE - Deactivate promocode
    /promo_stats CODE - Get promocode statistics

Examples:
    /create_promo WELCOME10 10 - 10% bonus, unlimited uses, never expires
    /create_promo VIP20 20 100 30 - 20% bonus, 100 uses max, expires in 30 days
"""

from datetime import datetime, timedelta
from decimal import Decimal

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from app.repo.db import get_session
from app.repo.promocode import PromocodeRepository
from config import ADMIN_TG_ID
from app.utils.logging import get_logger

router = Router()
LOG = get_logger(__name__)


def _is_admin(user_id: int) -> bool:
    """Check if user is admin"""
    return ADMIN_TG_ID and user_id == ADMIN_TG_ID


@router.message(Command("create_promo"))
async def create_promo_command(message: Message):
    """
    Create a new promocode.
    Usage: /create_promo CODE PERCENT [LIMIT] [DAYS]
    """
    if not _is_admin(message.from_user.id):
        return

    args = message.text.split()[1:]
    if len(args) < 2:
        await message.answer(
            "❌ Использование: /create_promo CODE PERCENT [LIMIT] [DAYS]\n\n"
            "Примеры:\n"
            "/create_promo WELCOME10 10 - 10% бонус, безлимит\n"
            "/create_promo VIP20 20 100 30 - 20% бонус, 100 активаций, 30 дней"
        )
        return

    code = args[0].upper().strip()
    try:
        percent = Decimal(args[1])
        if percent <= 0 or percent > 100:
            raise ValueError("Percent must be between 0 and 100")
    except (ValueError, IndexError):
        await message.answer("❌ Неверный процент бонуса (должен быть 0-100)")
        return

    usage_limit = 0  # Unlimited by default
    if len(args) > 2:
        try:
            usage_limit = int(args[2])
        except ValueError:
            await message.answer("❌ Неверный лимит использований")
            return

    expires_at = None
    if len(args) > 3:
        try:
            days = int(args[3])
            expires_at = datetime.utcnow() + timedelta(days=days)
        except ValueError:
            await message.answer("❌ Неверное количество дней")
            return

    async with get_session() as session:
        promo_repo = PromocodeRepository()
        promo = await promo_repo.create_promocode(
            code=code,
            reward_type="balance_bonus_percent",
            reward_value=percent,
            creator_id=message.from_user.id,
            description=f"Bonus {percent}% on deposit",
            usage_limit=usage_limit,
            expires_at=expires_at
        )

    if promo:
        text = (
            f"✅ Промокод создан!\n\n"
            f"Код: <code>{promo.code}</code>\n"
            f"Бонус: {promo.reward_value}% при пополнении\n"
            f"Лимит: {promo.usage_limit if promo.usage_limit > 0 else '∞'}\n"
            f"Истекает: {promo.expires_at.strftime('%Y-%m-%d %H:%M') if promo.expires_at else 'Никогда'}"
        )
        LOG.info(f"Admin {message.from_user.id} created promocode {code}")
    else:
        text = f"❌ Промокод {code} уже существует"

    await message.answer(text, parse_mode="HTML")


@router.message(Command("list_promos"))
async def list_promos_command(message: Message):
    """List all promocodes"""
    if not _is_admin(message.from_user.id):
        return

    async with get_session() as session:
        promo_repo = PromocodeRepository()
        promos = await promo_repo.list_promocodes()

    if not promos:
        await message.answer("📋 Промокодов нет")
        return

    text_lines = ["📋 <b>Список промокодов:</b>\n"]

    for promo in promos:
        status = "✅" if promo.active else "❌"
        usage = f"{promo.used_count}/{promo.usage_limit}" if promo.usage_limit > 0 else f"{promo.used_count}/∞"
        expires = promo.expires_at.strftime('%d.%m.%Y') if promo.expires_at else "∞"

        text_lines.append(
            f"{status} <code>{promo.code}</code> - {promo.reward_value}% бонус\n"
            f"   Активаций: {usage} | Истекает: {expires}\n"
        )

    await message.answer("\n".join(text_lines), parse_mode="HTML")


@router.message(Command("deactivate_promo"))
async def deactivate_promo_command(message: Message):
    """
    Deactivate a promocode.
    Usage: /deactivate_promo CODE
    """
    if not _is_admin(message.from_user.id):
        return

    args = message.text.split()[1:]
    if len(args) < 1:
        await message.answer("❌ Использование: /deactivate_promo CODE")
        return

    code = args[0].upper().strip()

    async with get_session() as session:
        promo_repo = PromocodeRepository()
        success = await promo_repo.deactivate_promocode(code)

    if success:
        text = f"✅ Промокод {code} деактивирован"
        LOG.info(f"Admin {message.from_user.id} deactivated promocode {code}")
    else:
        text = f"❌ Промокод {code} не найден"

    await message.answer(text)


@router.message(Command("promo_stats"))
async def promo_stats_command(message: Message):
    """
    Get promocode statistics.
    Usage: /promo_stats CODE
    """
    if not _is_admin(message.from_user.id):
        return

    args = message.text.split()[1:]
    if len(args) < 1:
        await message.answer("❌ Использование: /promo_stats CODE")
        return

    code = args[0].upper().strip()

    async with get_session() as session:
        promo_repo = PromocodeRepository()
        stats = await promo_repo.get_promocode_stats(code)

    if not stats:
        await message.answer(f"❌ Промокод {code} не найден")
        return

    text = (
        f"📊 <b>Статистика промокода {stats['code']}</b>\n\n"
        f"Описание: {stats['description']}\n"
        f"Бонус: {stats['reward_value']}%\n"
        f"Использовано: {stats['used_count']}\n"
        f"Лимит: {stats['usage_limit'] if stats['usage_limit'] > 0 else '∞'}\n"
        f"Статус: {'Активен ✅' if stats['active'] else 'Неактивен ❌'}\n"
        f"Создан: {stats['created_at'].strftime('%Y-%m-%d %H:%M')}\n"
        f"Истекает: {stats['expires_at'].strftime('%Y-%m-%d %H:%M') if stats['expires_at'] else 'Никогда'}"
    )

    await message.answer(text, parse_mode="HTML")
