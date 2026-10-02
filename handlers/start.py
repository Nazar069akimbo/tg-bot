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
    username = message.from_user.username or ""
    user = force_create_user(user_id, username)
    if not user:
        await message.answer("❌ Ошибка регистрации.")
        return

    profile = load_profile(user_id)
    name = profile.get("name") if profile else None

    # Если имени нет — спрашиваем
    if not name:
        helpers.user_pages[user_id] = {"state": "waiting_name"}
        await message.answer(
            "👋 Привет! Я — Vertex AI — твой умный ассистент.\n\n"
            "✨ Я умею:\n"
            "• 🖼️ Генерировать картинки\n"
            "• 🎨 Делать стикеры\n"
            "• 📄 Анализировать файлы (PDF, DOCX, TXT, CSV)\n"
            "• 🎤 Распознавать голосовые\n"
            "• 🔍 Искать в интернете\n"
            "• ⏰ Напоминать о важном\n"
            "• 🧠 Запоминать факты о тебе\n\n"
            "Просто напиши, что хочешь!\n\n"
            f"📧 Если что-то не работает — напиши админу: {ADMIN_EMAIL}\n\n"
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
    used, max_req = get_text_requests(user_id)

    text = (
        f"✨ Vertex AI\n\n"
        f"👋 Привет, {name}!\n"
        f"💰 Токенов: {tokens}\n"
        f"🖼️ 10 токенов = 1 картинка\n"
        f"📝 Текст: {used}/{max_req} запросов сегодня\n\n"
        f"{trial_text}\n\n"
        f"💬 Просто напиши, что хочешь!\n\n"
        f"📧 Проблемы? Пиши: {ADMIN_EMAIL}"
    )
    await message.answer(text, reply_markup=helpers.main_menu())
    logger.info(f"✅ [{user_id}] Бот запущен")
