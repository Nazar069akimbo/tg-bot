from aiogram import Router, types, F
from aiogram.filters import Command
from datetime import datetime
from database.db import *
from utils.user_storage import load_profile, load_meta, clear_memory
from . import helpers

router = Router()


async def show_profile(message: types.Message, user_id: int = None):
    if user_id is None:
        user_id = message.from_user.id
    force_create_user(user_id)
    user = get_user(user_id)
    if not user:
        await message.answer("❌ Пользователь не найден")
        return
    user = dict(user)

    profile = load_profile(user_id)
    meta = load_meta(user_id)
    name = profile.get("name") or "—"
    tokens = user.get("tokens") or 0
    plan = user.get("plan") or "basic"
    plan_name = {"basic": "Базовый", "premium": "Premium", "premium_plus": "Premium+"}.get(plan, plan)
    referral_count = get_referral_count(user_id)
    images_count = meta.get('images_count', 0)

    premium_until = user.get("premium_until")
    premium_line = ""
    if plan in ("premium", "premium_plus") and premium_until:
        try:
            until_dt = datetime.fromisoformat(premium_until)
            days_left = (until_dt - datetime.now()).days
            if days_left > 0:
                premium_line = f"\n⏳ Подписка до: <b>{until_dt.strftime('%d.%m.%Y')}</b> ({days_left} дн.)"
        except Exception:
            pass

    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"🪪 Имя: <b>{name}</b>\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"💳 Тариф: <b>{plan_name}</b>{premium_line}\n\n"
        f"🪙 Токенов: <b>{tokens}</b>\n"
        f"👥 Рефералов: {referral_count}\n"
        f"🖼️ Картинок создано: {images_count}"
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
    clear_memory(callback.from_user.id)
    await callback.message.edit_text("🧹 Готово! Я забыл всё о тебе.", reply_markup=helpers.main_menu())
    await helpers.safe_answer(callback, "✅ Память очищена", show_alert=True)
