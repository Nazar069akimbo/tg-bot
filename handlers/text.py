from aiogram import Router, types, F
from database.db import *
from ai.client import smart_reply, search_web
from . import helpers
from .image import generate_image
from utils.user_storage import set_user_name, add_fact
import logging

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.text)
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()

    if not text or text.startswith("/"):
        return

    state = helpers.user_pages.get(user_id, {})

    # Админ-ввод
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

    # === ИИ САМ РЕШАЕТ ===
    reminder_state = state if state.get("state") == "waiting_reminder_clarification" else None
    result = smart_reply(user_id, text, reminder_state=reminder_state)

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

        # Пробуем создать
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
        # Не смогли — спрашиваем
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
        status = await message.answer("🔍 Ищу...")
        answer = search_web(query)
        await status.edit_text(f"🔍 {answer}")
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

    # Неизвестное — просто отвечаем
    reply_text = result.get("reply", "")
    if reply_text:
        await message.answer(reply_text)
    else:
        await message.answer("Не понял. Попробуй ещё раз.")
