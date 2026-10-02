from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import *
from utils.user_storage import load_profile, set_user_name
from . import helpers
import logging

router = Router()
logger = logging.getLogger(__name__)
ADMIN_EMAIL = "mychannell@gmail.com"


@router.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id

    state = helpers.user_pages.get(user_id, {})
    if state.get("state") == "waiting_reminder_clarification":
        await message.answer("⏰ У тебя есть незавершённое напоминание.\n\nПродолжи или /cancel")
        return

    username = message.from_user.username or ""
    force_create_user(user_id, username)
    profile = load_profile(user_id)
    name = profile.get("name") if profile else None

    if not name:
        helpers.user_pages[user_id] = {"state": "waiting_name"}
        await message.answer(
            "👋 Привет! Я — Vertex AI — твой умный ассистент.\n\n"
            "✨ Я умею:\n"
            "• 🖼️ Генерировать картинки\n"
            "• 🎨 Делать стикеры\n"
            "• 📄 Анализировать файлы\n"
            "• 🎤 Распознавать голосовые\n"
            "• 🔍 Искать в интернете\n"
            "• ⏰ Напоминать\n"
            "• 🧠 Запоминать факты\n\n"
            f"📧 Проблемы? Пиши: {ADMIN_EMAIL}\n\n"
            "Как мне тебя называть?"
        )
        return

    args = message.text.split() if message.text else []
    if len(args) > 1 and args[1].isdigit():
        referrer_id = int(args[1])
        if referrer_id != user_id:
            success, msg = add_referral(referrer_id, user_id)
            if success:
                await message.answer(msg)

    if not has_trial(user_id) and get_tokens(user_id) == 0:
        activate_trial(user_id)
        trial_text = "🎁 20 токенов бесплатно на 3 дня!"
    else:
        trial_text = ""

    tokens = get_tokens(user_id)
    used, limit = get_daily_usage(user_id)
    left = limit - used

    text = (
        f"✨ Vertex AI\n\n"
        f"👋 Привет, {name}!\n"
        f"🪙 Токенов: {tokens}\n"
        f"📊 Дневной лимит: {left}/{limit}\n\n"
        f"{trial_text}\n\n"
        f"💬 Напиши, что хочешь!\n\n"
        f"📧 Проблемы? Пиши: {ADMIN_EMAIL}"
    )
    await message.answer(text, reply_markup=helpers.main_menu())
