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
    text_avail, text_limit = get_text_tokens_today(user_id)
    img_used, img_limit = get_week_images_used(user_id)
    referral_count = get_referral_count(user_id)

    text = (
        f"👤 **Профиль**\n\n"
        f"🪪 Имя: {name}\n"
        f"🆔 ID: {user_id}\n"
        f"💳 Тариф: {plan}\n\n"
        f"🪙 Токенов: {tokens}\n"
        f"📝 Текст: {text_avail}/{text_limit}\n"
        f"🎨 Картинок: {img_used}/{img_limit}\n"
        f"👥 Рефералов: {referral_count}\n"
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
    clear_memory(callback.from_user.id)
    await callback.message.edit_text("🧹 Готово! Я забыл всё о тебе.", reply_markup=helpers.main_menu())
    await helpers.safe_answer(callback, "✅ Память очищена", show_alert=True)
