from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from datetime import datetime, timedelta
import logging
import re

router = Router()
logger = logging.getLogger(__name__)


def _build_datetime(date_str, time_str):
    now = datetime.now()
    today = now.date()
    if not time_str:
        return None
    try:
        time_obj = datetime.strptime(time_str, "%H:%M").time()
    except ValueError:
        return None

    if date_str in (None, "", "today", "сегодня"):
        full = datetime.combine(today, time_obj)
        if full < now:
            full += timedelta(days=1)
        return full
    elif date_str in ("tomorrow", "завтра"):
        return datetime.combine(today + timedelta(days=1), time_obj)
    else:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            return datetime.combine(d, time_obj)
        except ValueError:
            return None


def reminders_kb(reminders):
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for r in reminders:
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=f"❌ Удалить: {r['text'][:20]}", callback_data=f"del_reminder_{r['id']}")
        ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🗑️ Удалить все", callback_data="del_all_reminders")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")])
    return kb


async def create_reminder_from_ai(message: types.Message, params: dict):
    user_id = message.from_user.id
    text = params.get("text", "").strip()
    time_str = params.get("time", "").strip()
    date_str = params.get("date", "").strip()
    need_clarification = params.get("need_clarification", False)
    question = params.get("question", "")

    if need_clarification:
        helpers.user_pages[user_id] = {
            "state": "waiting_reminder_clarification",
            "text": text, "time": time_str, "date": date_str, "question": question
        }
        await message.answer(f"❓ {question}\n\n⏹ /cancel — отмена")
        return

    if not text or not time_str:
        await message.answer("❌ Не понял. Напиши: «Напомни завтра в 10 купить хлеб»")
        return

    full_time = _build_datetime(date_str, time_str)
    if not full_time:
        await message.answer("❌ Не понял дату или время.")
        return

    add_reminder(user_id, text, full_time.isoformat())
    await message.answer(
        f"⏰ **Напоминание установлено!**\n\n"
        f"📝 {text}\n🕐 {full_time.strftime('%d.%m.%Y %H:%M')}"
    )
    logger.info(f"⏰ [{user_id}] {text} на {full_time}")


async def handle_clarification(message: types.Message, text: str):
    user_id = message.from_user.id
    state = helpers.user_pages.get(user_id, {})

    if text.strip() == "/cancel":
        helpers.user_pages.pop(user_id, None)
        await message.answer("✅ Отменено", reply_markup=helpers.main_menu())
        return

    time_str = state.get("time", "")
    date_str = state.get("date", "")

    if re.match(r'^\d{1,2}:\d{2}$', text.strip()):
        time_str = text.strip()
    else:
        date_str = text.strip().lower()

    full_time = _build_datetime(date_str, time_str)
    if not full_time:
        await message.answer("❌ Не понял. Уточни: во сколько и на какой день?")
        return

    add_reminder(user_id, state.get("text", ""), full_time.isoformat())
    helpers.user_pages.pop(user_id, None)
    await message.answer(
        f"⏰ **Напоминание установлено!**\n\n"
        f"📝 {state.get('text', '')}\n🕐 {full_time.strftime('%d.%m.%Y %H:%M')}"
    )


async def list_reminders_msg(message: types.Message, user_id: int = None):
    if user_id is None:
        user_id = message.from_user.id
    reminders = get_user_reminders(user_id)
    if not reminders:
        await message.answer("📭 Нет активных напоминаний", reply_markup=helpers.main_menu())
        return

    text = "⏰ **Напоминания (ближайшие первыми):**\n\n"
    for i, r in enumerate(reminders, 1):
        try:
            time_str = datetime.fromisoformat(r['time']).strftime('%d.%m %H:%M')
        except Exception:
            time_str = r['time']
        text += f"{i}. 🕐 {time_str} — {r['text']}\n"

    await message.answer(text, reply_markup=reminders_kb(reminders))


@router.message(Command("remind"))
async def set_reminder_cmd(message: types.Message):
    text = message.text.replace("/remind", "").strip()
    if not text:
        await message.answer("❌ Формат: /remind 10:00 Текст")
        return
    try:
        parts = text.split(" ", 1)
        if len(parts) < 2:
            await message.answer("❌ Формат: /remind 10:00 Текст")
            return
        time_str, reminder_text = parts[0], parts[1]
        full_time = _build_datetime("today", time_str)
        if not full_time:
            await message.answer("❌ Неверное время.")
            return
        add_reminder(message.from_user.id, reminder_text, full_time.isoformat())
        await message.answer(
            f"⏰ **Напоминание установлено!**\n\n"
            f"📝 {reminder_text}\n🕐 {full_time.strftime('%d.%m.%Y %H:%M')}"
        )
    except Exception:
        await message.answer("❌ Формат: /remind 10:00 Текст")


@router.message(Command("reminders"))
async def list_reminders_cmd(message: types.Message):
    await list_reminders_msg(message)


@router.callback_query(F.data == "my_reminders")
async def my_reminders_cb(callback: types.CallbackQuery):
    reminders = get_user_reminders(callback.from_user.id)
    if not reminders:
        await callback.message.answer("📭 Нет активных напоминаний", reply_markup=helpers.main_menu())
        await helpers.safe_answer(callback)
        return

    text = "⏰ **Напоминания (ближайшие первыми):**\n\n"
    for i, r in enumerate(reminders, 1):
        try:
            time_str = datetime.fromisoformat(r['time']).strftime('%d.%m %H:%M')
        except Exception:
            time_str = r['time']
        text += f"{i}. 🕐 {time_str} — {r['text']}\n"

    await callback.message.edit_text(text, reply_markup=reminders_kb(reminders))
    await helpers.safe_answer(callback)


@router.callback_query(F.data.startswith("del_reminder_"))
async def del_reminder_cb(callback: types.CallbackQuery):
    try:
        reminder_id = int(callback.data.replace("del_reminder_", ""))
    except ValueError:
        await helpers.safe_answer(callback, "❌ Ошибка", show_alert=True)
        return

    delete_reminder(reminder_id)
    await helpers.safe_answer(callback, "✅ Удалено", show_alert=True)
    await my_reminders_cb(callback)


@router.callback_query(F.data == "del_all_reminders")
async def del_all_reminders_cb(callback: types.CallbackQuery):
    delete_all_reminders(callback.from_user.id)
    await callback.message.edit_text("🗑️ Все напоминания удалены", reply_markup=helpers.main_menu())
    await helpers.safe_answer(callback)
