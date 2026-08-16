from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import *
from . import helpers
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    logger.info(f"📌 [{user_id}] start")
    
    username = message.from_user.username or ""
    user = force_create_user(user_id, username)
    if not user:
        await message.answer("❌ Ошибка регистрации.")
        return

    memory = get_user_memory(user_id)
    if not memory or not memory.get('name'):
        helpers.user_pages[user_id] = {"state": "waiting_name"}
        await message.answer(
            "👋 Привет! Я — **Vertex AI** — твой умный ассистент.\n\n"
            "✨ Я умею:\n"
            "• 🖼️ Генерировать картинки\n"
            "• ✏️ Редактировать картинки\n"
            "• 📄 Анализировать файлы (PDF, DOCX, TXT, CSV)\n"
            "• 🎤 Распознавать голосовые\n"
            "• 🔍 Искать в интернете\n"
            "• ⏰ Напоминать о важном\n"
            "• 🧠 Отвечать на вопросы\n\n"
            "Просто напиши, что хочешь!\n\n"
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
    name = helpers.get_user_name(user_id) or "друг"

    text = (
        f"✨ **Vertex AI**\n\n"
        f"👋 С возвращением, {name}!\n"
        f"💰 Токенов: {tokens}\n"
        f"🖼️ 10 токенов = 1 картинка\n"
        f"📝 Текст: {used}/{max_req} запросов сегодня\n\n"
        f"{trial_text}\n\n"
        f"💬 Просто напиши, что хочешь!"
    )
    await message.answer(text, reply_markup=helpers.main_menu())
    logger.info(f"✅ [{user_id}] Бот запущен")

@router.message(Command("help"))
async def help_cmd(message: types.Message):
    text = (
        "❓ **Помощь**\n\n"
        "🖼️ **Картинка** — *нарисуй кота*\n"
        "✏️ **Правка** — *сделай кота чёрным*\n"
        "📄 **Файл** — отправь PDF, DOCX, TXT, CSV\n"
        "🎤 **Голосовое** — отправь голосовое\n"
        "🔍 **Поиск** — /search запрос\n"
        "⏰ **Напоминание** — /remind 10:00 текст\n"
        "💰 **Цены** — *сколько стоит премиум*\n"
        "📊 **Баланс** — *мой баланс*\n"
        "👥 **Рефералы** — *как пригласить друга*\n\n"
        "📌 Команды: /start, /balance, /profile, /help"
    )
    await message.answer(text, reply_markup=helpers.main_menu())

@router.message(Command("profile"))
async def profile_cmd(message: types.Message):
    user_id = message.from_user.id
    tokens = get_tokens(user_id)
    name = helpers.get_user_name(user_id) or "Не указано"
    await message.answer(
        f"👤 **Мой профиль**\n\n"
        f"🆔 ID: {user_id}\n"
        f"👤 Имя: {name}\n"
        f"💰 Токенов: {tokens}\n"
        f"🖼️ Картинок: {tokens // 10}",
        reply_markup=helpers.main_menu()
    )

@router.message(Command("cancel"))
async def cancel_cmd(message: types.Message):
    helpers.user_pages.pop(message.from_user.id, None)
    await message.answer("✅ Отменено", reply_markup=helpers.main_menu())
