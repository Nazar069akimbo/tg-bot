from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import *
from utils.user_storage import load_profile, set_user_name
from . import helpers
import os, logging

router = Router()
logger = logging.getLogger(__name__)
ADMIN_EMAIL = "mychannell069@gmail.com"
ADMIN_ID = int(os.getenv('ADMIN_ID', 6957852385))


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

    # Проверяем — новый ли юзер
    is_new = not has_trial(user_id) and get_tokens(user_id) == 0

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

    # Триал
    if is_new:
        activate_trial(user_id)
        trial_text = "🎁 30 токенов новичку — трать на что хочешь!"
    else:
        trial_text = ""

    tokens = get_tokens(user_id)
    user = get_user(user_id)
    plan = dict(user).get("plan", "basic") if user else "basic"

    text_avail, text_limit = get_text_tokens_today(user_id)
    img_used, img_limit = get_week_images_used(user_id)

    if tokens > 0:
        balance_line = f"🪙 Токенов: {tokens} (без лимитов)"
    else:
        balance_line = (
            f"📝 Текст: {text_avail}/{text_limit} сегодня\n"
            f"🎨 Картинок: {img_used}/{img_limit} на этой неделе"
        )

    text = (
        f"✨ Vertex AI\n\n"
        f"👋 Привет, {name}!\n"
        f"💳 Тариф: {plan}\n"
        f"{balance_line}\n\n"
        f"{trial_text}\n\n"
        f"💬 Напиши, что хочешь!\n\n"
        f"📧 Проблемы? Пиши: {ADMIN_EMAIL}"
    )
    await message.answer(text, reply_markup=helpers.main_menu())

    # Уведомление админу о новом юзере
    if is_new:
        try:
            notif_text = (
                f"🆕 **Новый пользователь!**\n\n"
                f"👤 {message.from_user.full_name}\n"
                f"🔗 @{message.from_user.username or '—'}\n"
                f"🆔 {user_id}"
            )
            await message.bot.send_message(ADMIN_ID, notif_text)
            logger.info(f"📩 Уведомление о новом юзере {user_id}")
        except Exception as e:
            logger.warning(f"⚠️ Не отправил уведомление: {e}")
            try:
                add_admin_notification(notif_text, user_id)
            except Exception:
                pass
