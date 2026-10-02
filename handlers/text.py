from aiogram import Router, types, F
from database.db import *
from ai.client import smart_reply, search_web
from . import helpers
from .image import generate_image
from utils.user_storage import set_user_name, add_fact
import logging
import asyncio
import os

router = Router()
logger = logging.getLogger(__name__)

# Публичные GIF (можно заменить на свои)
THINKING_GIFS = [
    "https://media.giphy.com/media/3o7aCSPqXE5C6T8tBC/giphy.gif",
    "https://media.giphy.com/media/l0HlHFRbmaZtBRhXG/giphy.gif",
    "https://media.giphy.com/media/xTk9ZvMnbIiXv7qPzW/giphy.gif",
]

THINKING_TEXTS = [
    "🤔 Думаю...",
    "🧠 Анализирую...",
    "💭 Обрабатываю...",
    "⚙️ Секунду...",
]

# Кэш file_id (чтобы не скачивать каждый раз)
_gif_file_cache = {}


async def get_thinking_gif_file_id(bot) -> str:
    """Возвращает file_id GIF. При первом вызове — скачивает и кэширует."""
    global _gif_file_cache
    cache_key = "thinking"
    if cache_key in _gif_file_cache:
        return _gif_file_cache[cache_key]

    # Пробуем получить из БД
    try:
        saved = get_setting("thinking_gif_file_id")
        if saved:
            _gif_file_cache[cache_key] = saved
            return saved
    except Exception:
        pass

    # Первый раз — отправляем GIF в чат (бот сам себе, но нужен chat_id)
    # Проще: используем готовый file_id из giphy — Telegram сам подгрузит по URL
    # Но Bot API не умеет скачивать по URL — нужен upload.
    # Поэтому просто вернём None и покажем текст.
    return None


async def show_thinking_status(message: types.Message):
    """Показывает анимированный статус ожидания."""
    # Пробуем с гифкой
    gif_id = None
    try:
        gif_id = get_setting("thinking_gif_file_id")
    except Exception:
        pass

    if gif_id:
        try:
            status = await message.answer_animation(gif_id, caption=THINKING_TEXTS[0])
            return status, True
        except Exception as e:
            logger.warning(f"⚠️ GIF не сработала: {e}")

    # Fallback — текст
    status = await message.answer(THINKING_TEXTS[0])
    return status, False


async def animate_status(status_msg: types.Message, is_gif: bool, stop_event: asyncio.Event):
    """Меняет текст каждые 2.5 сек, пока не остановят."""
    i = 1
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=2.5)
            break
        except asyncio.TimeoutError:
            pass
        if stop_event.is_set():
            break
        try:
            if is_gif:
                await status_msg.edit_caption(caption=THINKING_TEXTS[i % len(THINKING_TEXTS)])
            else:
                await status_msg.edit_text(THINKING_TEXTS[i % len(THINKING_TEXTS)])
            i += 1
        except Exception:
            pass


@router.message(F.text)
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()

    if not text or text.startswith("/"):
        return

    state = helpers.user_pages.get(user_id, {})

    if state.get("state") in ["waiting_broadcast", "waiting_block_user", "waiting_contact",
                              "waiting_give_tokens", "waiting_price", "waiting_promo_code",
                              "waiting_tariff_edit", "waiting_tariff_add"]:
        from .admin import handle_admin_input
        await handle_admin_input(message)
        return

    if state.get("state") == "waiting_promo_use":
        success, msg = use_promocode(text.upper(), user_id)
        await message.answer(msg, reply_markup=helpers.main_menu())
        helpers.user_pages.pop(user_id, None)
        return

    if state.get("state") == "waiting_name":
        set_user_name(user_id, text)
        helpers.user_pages.pop(user_id, None)
        await message.answer(f"Ок, {text}! Приятно познакомиться 😊")
        from .start import start_cmd
        await start_cmd(message)
        return

    # === АНИМИРОВАННЫЙ СТАТУС ===
    status_msg, is_gif = await show_thinking_status(message)
    stop_event = asyncio.Event()
    anim_task = asyncio.create_task(animate_status(status_msg, is_gif, stop_event))

    # === ИИ ===
    reminder_state = state if state.get("state") == "waiting_reminder_clarification" else None
    result = smart_reply(user_id, text, reminder_state=reminder_state)

    # Останавливаем анимацию
    stop_event.set()
    try:
        await asyncio.wait_for(anim_task, timeout=1.0)
    except Exception:
        pass

    try:
        await status_msg.delete()
    except Exception:
        pass

    action = result.get("action", "reply")

    if action == "reply":
        reply_text = result.get("reply", "")
        if reply_text:
            await message.answer(reply_text)
        else:
            await message.answer("Не понял. Попробуй переформулировать.")
        if reminder_state:
            helpers.user_pages.pop(user_id, None)
        return

    if action == "generate_image":
        prompt = result.get("prompt", text)
        await generate_image(message, prompt)
        return

    if action == "set_reminder":
        r_text = (result.get("text") or "").strip()
        r_time = (result.get("time") or "").strip()
        r_date = (result.get("date") or "").strip()
        need_clar = result.get("need_clarification", False)
        question = result.get("question", "")
        reply_text = result.get("reply", "")

        helpers.user_pages[user_id] = {
            "state": "waiting_reminder_clarification",
            "text": r_text,
            "time": r_time,
            "date": r_date,
            "question": question
        }

        if need_clar:
            if reply_text:
                await message.answer(reply_text)
            elif question:
                await message.answer(f"❓ {question}")
            else:
                await message.answer("❓ Уточни, пожалуйста.")
            return

        if r_text and r_time:
            full_time = helpers.build_reminder_time(r_date, r_time)
            if full_time:
                add_reminder(user_id, r_text, full_time.isoformat())
                helpers.user_pages.pop(user_id, None)
                await message.answer(
                    f"⏰ Напоминание установлено!\n\n"
                    f"📝 {r_text}\n"
                    f"🕐 {full_time.strftime('%d.%m.%Y %H:%M')}"
                )
                return
        if reply_text:
            await message.answer(reply_text)
        elif question:
            await message.answer(f"❓ {question}")
        else:
            await message.answer("❓ Уточни, пожалуйста.")
        return

    if action == "cancel_reminder":
        helpers.user_pages.pop(user_id, None)
        reply_text = result.get("reply", "✅ Отменено")
        await message.answer(reply_text, reply_markup=helpers.main_menu())
        return

    if action == "delete_reminder":
        target = result.get("text", "")
        if target:
            delete_reminder_by_text(user_id, target)
            await message.answer(f"✅ Удалено: {target}")
        else:
            await message.answer("❌ Не понял, какое напоминание удалить")
        return

    if action == "delete_all_reminders":
        delete_all_reminders(user_id)
        await message.answer("🗑️ Все напоминания удалены")
        return

    if action == "list_reminders":
        from .reminders import list_reminders_msg
        await list_reminders_msg(message)
        return

    if action == "search_web":
        query = result.get("query", text)
        search_status = await message.answer("🔍 Ищу...")
        answer = search_web(query)
        await search_status.edit_text(f"🔍 {answer}")
        return

    if action == "remember":
        fact = result.get("fact", "").strip()
        reply_text = result.get("reply", "").strip()
        if fact:
            add_fact(user_id, fact)
        if reply_text:
            await message.answer(reply_text)
        else:
            await message.answer("Запомнил 😊")
        return

    reply_text = result.get("reply", "")
    if reply_text:
        await message.answer(reply_text)
    else:
        await message.answer("Не понял. Попробуй ещё раз.")
