from aiogram import Router, types, F
from aiogram.filters import Command
from datetime import datetime
from database.db import *
from utils.user_storage import load_profile, load_meta, load_history, clear_memory
from . import helpers

router = Router()


def get_plan_name(plan):
    plans = {
        "basic": "Базовый",
        "premium": "💎 Премиум",
        "premium_plus": "👑 Премиум+",
    }
    return plans.get(plan, "Базовый")


async def show_profile(message: types.Message, user_id: int = None):
    if user_id is None:
        user_id = message.from_user.id

    force_create_user(user_id)
    user = get_user(user_id)
    if not user:
        await message.answer("❌ Пользователь не найден", reply_markup=helpers.main_menu())
        return
    user = dict(user)

    profile = load_profile(user_id)
    meta = load_meta(user_id)
    history = load_history(user_id)
    prefs = profile.get("preferences", {})

    name = profile.get("name") or "—"
    tokens = user.get("tokens") or 0
    plan = user.get("plan") or "basic"
    plan_name = get_plan_name(plan)

    premium_until = user.get("premium_until")
    premium_line = ""
    if premium_until and plan != "basic":
        try:
            until_date = datetime.fromisoformat(premium_until)
            premium_line = f"\n👑 Действует до: {until_date.strftime('%d.%m.%Y')}"
        except Exception:
            pass

    joined = user.get("joined") or ""
    joined_line = ""
    if joined:
        try:
            joined_date = datetime.fromisoformat(joined)
            joined_line = f"📅 С нами с: {joined_date.strftime('%d.%m.%Y')}"
        except Exception:
            pass

    used, max_req = get_text_requests(user_id)
    referral_count = get_referral_count(user_id)

    hobbies = ", ".join(prefs.get("hobbies") or []) or "—"
    colors = prefs.get("colors") or "—"
    style = prefs.get("style") or "—"

    text = (
        f"👤 Профиль\n\n"
        f"🪪 Имя: {name}\n"
        f"🆔 ID: {user_id}\n"
        f"💳 Тариф: {plan_name}{premium_line}\n\n"
        f"💰 Токенов: {tokens}\n"
        f"🖼️ Хватит на: {tokens // 10} картинок\n"
        f"📝 Текст: {used}/{max_req} сегодня\n"
        f"👥 Рефералов: {referral_count}\n"
        f"{joined_line}\n\n"
        f"🧠 Что я о тебе знаю:\n"
        f"🎯 Хобби: {hobbies}\n"
        f"🌈 Цвета: {colors}\n"
        f"🎨 Стиль: {style}\n"
        f"📚 Сообщений: {len(history)}\n"
        f"🖼️ Картинок: {meta.get('images_count', 0)}"
    )
    try:
        await message.edit_text(text, reply_markup=helpers.profile_kb())
    except Exception:
        await message.answer(text, reply_markup=helpers.profile_kb())


@router.message(Command("profile"))
async def profile_command(message: types.Message):
    await show_profile(message)


@router.callback_query(F.data == "profile")
async def profile_cb(callback: types.CallbackQuery):
    await show_profile(callback.message, callback.from_user.id)
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "forget_all")
async def forget_all_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    clear_memory(user_id)
    await callback.message.edit_text(
        "🧹 Готово!\n\nЯ забыл всё, что знал о тебе: имя, хобби, историю диалогов.\n\n"
        "Картинки остались в сохранности.",
        reply_markup=helpers.main_menu()
    )
    await helpers.safe_answer(callback, "✅ Память очищена", show_alert=True)
