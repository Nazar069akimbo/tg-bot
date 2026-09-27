from aiogram import Router, types, F
from aiogram.filters import Command
from datetime import datetime
from database.db import *
from . import helpers

router = Router()


def get_plan_name(plan):
    plans = {
        "basic": "Базовый",
        "premium": "💎 Премиум",
        "premium_plus": "👑 Премиум+",
        "premium_deluxe": "👑 Премиум+",
    }
    return plans.get(plan, "Базовый")


async def show_profile(message: types.Message, user_id: int = None):
    """Показать профиль. user_id можно передать явно (для callback'ов)."""
    if user_id is None:
        user_id = message.from_user.id

    force_create_user(user_id)
    user = get_user(user_id)
    if not user:
        await message.answer("❌ Пользователь не найден", reply_markup=helpers.main_menu())
        return

    memory = get_user_memory(user_id)
    name = (memory or {}).get("name") or "—"

    tokens = user["tokens"] or 0
    plan = user["plan"] or "basic"
    plan_name = get_plan_name(plan)

    premium_until = user.get("premium_until")
    premium_line = ""
    if premium_until and plan != "basic":
        try:
            until_date = datetime.fromisoformat(premium_until)
            premium_line = f"\n👑 Действует до: {until_date.strftime('%d.%m.%Y')}"
        except Exception:
            pass

    joined = user.get("joined", "")
    joined_line = ""
    if joined:
        try:
            joined_date = datetime.fromisoformat(joined)
            joined_line = f"📅 С нами с: {joined_date.strftime('%d.%m.%Y')}"
        except Exception:
            pass

    used, max_req = get_text_requests(user_id)
    referral_count = get_referral_count(user_id)

    text = (
        f"👤 **Профиль**\n\n"
        f"🪪 Имя: {name}\n"
        f"🆔 ID: {user_id}\n"
        f"💳 Тариф: {plan_name}{premium_line}\n\n"
        f"💰 Токенов: {tokens}\n"
        f"🖼️ Хватит на: {tokens // 10} картинок\n"
        f"📝 Текст: {used}/{max_req} сегодня\n"
        f"👥 Рефералов: {referral_count}\n"
        f"{joined_line}"
    )
    await message.answer(text, reply_markup=helpers.main_menu())


@router.message(Command("profile"))
async def profile_command(message: types.Message):
    await show_profile(message)


@router.callback_query(F.data == "profile")
async def profile_cb(callback: types.CallbackQuery):
    # ВАЖНО: id берём из callback.from_user (callback.message.from_user — это бот)
    await show_profile(callback.message, callback.from_user.id)
    await helpers.safe_answer(callback)