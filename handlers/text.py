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

    # Проверка: спрашивать ли модель
    ask_model = get_setting(f"ask_model_{user_id}") != "no"

    if ask_model:
        user = get_user(user_id)
        plan = dict(user).get("plan", "basic") if user else "basic"
        used, limit = get_daily_usage(user_id)
        balance = limit - used
        current_model = get_model_setting("text_chat") or "gpt-4.1-nano"

        await message.answer(
            f"🧠 Выбери модель ({balance}/{limit} запросов):",
            reply_markup=helpers.model_choice_kb("text_chat", current_model, plan, balance)
        )
        helpers.user_pages[user_id] = {"state": "waiting_model_choice", "pending_text": text}
        return

    await process_text(message, user_id, text, state)


async def process_text(message: types.Message, user_id: int, text: str, state: dict):
    user = get_user(user_id)
    if not user:
        force_create_user(user_id)
        user = get_user(user_id)
    user = dict(user)
    plan = user.get("plan") or "basic"

    used, limit = get_daily_usage(user_id)
    current_model = get_model_setting("text_chat") or "gpt-4.1-nano"
    cost = helpers.MODEL_COSTS.get(current_model, 1)

    user_level = helpers.PLAN_LEVEL.get(plan, 0)
    required = helpers.MODEL_MIN_LEVEL.get(current_model, 0)

    if required > user_level:
        await message.answer(f"🔒 Модель {helpers.MODEL_NAMES.get(current_model)} доступна только на Premium.\nОформи: /credits")
        return

    if used + cost > limit:
        await message.answer(f"🔒 Лимит на сегодня исчерпан ({used}/{limit}).")
        return

    spend_daily_requests(user_id, cost)

    status_msg = await message.answer("🤔 Думаю...")

    reminder_state = state if state.get("state") == "waiting_reminder_clarification" else None
    result = smart_reply(user_id, text, reminder_state=reminder_state)

    try:
        await status_msg.delete()
    except Exception:
        pass

    action = result.get("action", "reply")

    if action == "reply":
        reply_text = result.get("reply", "")
        await message.answer(reply_text or "Не понял.")
        if reminder_state:
            helpers.user_pages.pop(user_id, None)
        return

    if action == "generate_image":
        await generate_image(message, result.get("prompt", text))
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
            "text": r_text, "time": r_time, "date": r_date, "question": question
        }

        if need_clar:
            await message.answer(reply_text or f"❓ {question}" or "❓ Уточни.")
            return

        if r_text and r_time:
            full_time = helpers.build_reminder_time(r_date, r_time)
            if full_time:
                add_reminder(user_id, r_text, full_time.isoformat())
                helpers.user_pages.pop(user_id, None)
                await message.answer(f"⏰ Напоминание установлено!\n\n📝 {r_text}\n🕐 {full_time.strftime('%d.%m.%Y %H:%M')}")
                return
        await message.answer(reply_text or f"❓ {question}" or "❓ Уточни.")
        return

    if action == "cancel_reminder":
        helpers.user_pages.pop(user_id, None)
        await message.answer(result.get("reply", "✅ Отменено"), reply_markup=helpers.main_menu())
        return

    if action == "delete_reminder":
        target = result.get("text", "")
        if target:
            delete_reminder_by_text(user_id, target)
            await message.answer(f"✅ Удалено: {target}")
        else:
            await message.answer("❌ Не понял")
        return

    if action == "delete_all_reminders":
        delete_all_reminders(user_id)
        await message.answer("🗑️ Все удалены")
        return

    if action == "list_reminders":
        from .reminders import list_reminders_msg
        await list_reminders_msg(message)
        return

    if action == "search_web":
        search_status = await message.answer("🔍 Ищу...")
        answer = search_web(result.get("query", text))
        await search_status.edit_text(f"🔍 {answer}")
        return

    if action == "remember":
        fact = result.get("fact", "").strip()
        reply_text = result.get("reply", "").strip()
        if fact:
            add_fact(user_id, fact)
        await message.answer(reply_text or "Запомнил 😊")
        return

    await message.answer(result.get("reply", "Не понял."))


@router.callback_query(F.data.startswith("pickmodel_"))
async def pick_model_cb(callback: types.CallbackQuery):
    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        await helpers.safe_answer(callback, "❌ Ошибка", show_alert=True)
        return
    task = parts[1]
    model_id = parts[2]

    # === ПРОВЕРКА ДОСТУПА ===
    user = get_user(callback.from_user.id)
    plan = dict(user).get("plan", "basic") if user else "basic"
    user_level = helpers.PLAN_LEVEL.get(plan, 0)
    required = helpers.MODEL_MIN_LEVEL.get(model_id, 0)

    if required > user_level:
        await helpers.safe_answer(callback, "🔒 Модель доступна только на Premium", show_alert=True)
        return

    set_model_setting(task, model_id)

    state = helpers.user_pages.get(callback.from_user.id, {})
    pending_text = state.get("pending_text")
    pending_prompt = state.get("pending_prompt")

    if pending_text:
        helpers.user_pages.pop(callback.from_user.id, None)
        try:
            await callback.message.delete()
        except Exception:
            pass
        await process_text(callback.message, callback.from_user.id, pending_text, {})
    elif pending_prompt:
        helpers.user_pages.pop(callback.from_user.id, None)
        try:
            await callback.message.delete()
        except Exception:
            pass
        await generate_image(callback.message, pending_prompt, callback.from_user.id)
    else:
        try:
            await callback.message.edit_text(f"✅ Модель: {helpers.MODEL_NAMES.get(model_id, model_id)}")
        except Exception:
            pass
    await helpers.safe_answer(callback)


@router.callback_query(F.data.startswith("always_"))
async def always_model_cb(callback: types.CallbackQuery):
    task = callback.data.replace("always_", "")
    set_setting(f"ask_model_{callback.from_user.id}", "no")
    if task == "image_generate":
        set_setting(f"ask_image_model_{callback.from_user.id}", "no")

    state = helpers.user_pages.get(callback.from_user.id, {})
    pending_text = state.get("pending_text")
    pending_prompt = state.get("pending_prompt")

    if pending_text:
        helpers.user_pages.pop(callback.from_user.id, None)
        try:
            await callback.message.delete()
        except Exception:
            pass
        await process_text(callback.message, callback.from_user.id, pending_text, {})
    elif pending_prompt:
        helpers.user_pages.pop(callback.from_user.id, None)
        try:
            await callback.message.delete()
        except Exception:
            pass
        await generate_image(callback.message, pending_prompt, callback.from_user.id)
    else:
        try:
            await callback.message.edit_text("✅ Больше не спрашиваю.")
        except Exception:
            pass
    await helpers.safe_answer(callback)
