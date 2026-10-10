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

    is_new = not has_trial(user_id) and get_tokens(user_id) == 0

    if not name:
        helpers.user_pages[user_id] = {"state": "waiting_name"}
        await message.answer(
            "👋 Привет! Я — <b>Vertex AI</b> — твой умный ассистент.\n\n"
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

    if is_new:
        activate_trial(user_id)
        trial_text = "🎁 <b>30 токенов новичку</b> — трать на что хочешь!\n\n"
    else:
        trial_text = ""

    tokens = get_tokens(user_id)
    user = get_user(user_id)
    plan = dict(user).get("plan", "basic") if user else "basic"
    plan_name = {"basic": "Базовый", "premium": "Premium", "premium_plus": "Premium+"}.get(plan, plan)

    if tokens > 0:
        balance_line = f"🪙 Токенов: <b>{tokens}</b>"
    else:
        balance_line = "🪙 Токенов: <b>0</b>\n💎 Купи токены: /credits"

    text = (
        f"✨ <b>Vertex AI</b>\n\n"
        f"👋 Привет, <b>{name}</b>!\n"
        f"💳 Тариф: {plan_name}\n"
        f"{balance_line}\n\n"
        f"{trial_text}"
        f"💬 Напиши, что хочешь!\n\n"
        f"📧 Проблемы? Пиши: {ADMIN_EMAIL}"
    )
    await message.answer(text, reply_markup=helpers.main_menu())

    if is_new:
        try:
            notif_text = (
                f"🆕 <b>Новый пользователь!</b>\n\n"
                f"👤 {message.from_user.full_name}\n"
                f"🔗 @{message.from_user.username or '—'}\n"
                f"🆔 <code>{user_id}</code>"
            )
            await message.bot.send_message(ADMIN_ID, notif_text)
            logger.info(f"📩 Уведомление о новом юзере {user_id}")
        except Exception as e:
            logger.warning(f"⚠️ Не отправил уведомление: {e}")
            try:
                add_admin_notification(notif_text, user_id)
            except Exception:
                pass
