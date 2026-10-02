from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from . import helpers
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

    time_str = str(time_str).strip().lower()
    date_str = str(date_str or "").strip().lower()

    m = re.match(r'через\s+(\d+)\s*(мин|минут|час|часов|дн|дней|день)', time_str)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        if unit.startswith('мин'):
            return now + timedelta(minutes=amount)
        elif unit.startswith('час'):
            return now + timedelta(hours=amount)
        elif unit.startswith('дн'):
            return now + timedelta(days=amount)

    m = re.match(r'через\s+(\d+)$', time_str)
    if m:
        return now + timedelta(minutes=int(m.group(1)))

    # "12.00", "12:00", "12,00"
    time_str = time_str.replace(".", ":").replace(",", ":")
    m = re.match(r'^(\d{1,2}):(\d{2})$', time_str)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        time_obj = datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time()

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
                if d < today:
                    full = datetime.combine(today, time_obj)
                    if full < now:
                        full += timedelta(days=1)
                    return full
                return datetime.combine(d, time_obj)
            except ValueError:
                return None

    return None


def reminders_kb(reminders):
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for r in reminders:
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=f"❌ {r['text'][:25]}", callback_data=f"del_reminder_{r['id']}")
        ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🗑️ Удалить все", callback_data="del_all_reminders")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")])
    return kb


def no_reminders_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
    ])


async def create_reminder_from_ai(message: types.Message, params: dict):
    user_id = message.from_user.id
    text = (params.get("text") or "").strip()
    time_str = (params.get("time") or "").strip()
    date_str = (params.get("date") or "").strip()
    need_clarification = params.get("need_clarification", False)
    question = params.get("question", "")

    helpers.user_pages[user_id] = {
        "state": "waiting_reminder_clarification",
        "text": text,
        "time": time_str,
        "date": date_str,
        "question": question
    }

    # Если ИИ просит уточнить — задаём его вопрос
    if need_clarification and question:
        await message.answer(f"❓ {question}\n\n⏹ /cancel — отмена")
        return

    # Если всё есть — создаём
    if text and time_str:
        full_time = _build_datetime(date_str, time_str)
        if full_time:
            add_reminder(user_id, text, full_time.isoformat())
            helpers.user_pages.pop(user_id, None)
            await message.answer(
                f"⏰ Напоминание установлено!\n\n"
                f"📝 {text}\n"
                f"🕐 {full_time.strftime('%d.%m.%Y %H:%M')}"
            )
            return

    # Если чего-то не хватает — спрашиваем сами (fallback)
    if not text:
        question = "Что напомнить?"
    elif not time_str:
        question = "Во сколько напомнить?"
    elif not date_str:
        question = "На какой день? Сегодня, завтра или дата?"
    else:
        question = "Уточни, пожалуйста."

    helpers.user_pages[user_id]["question"] = question
    await message.answer(f"❓ {question}\n\n⏹ /cancel — отмена")


async def handle_clarification(message: types.Message, text: str):
    """
    ИИ полностью управляет диалогом: отвечает, спрашивает, решает, что собрано.
    """
    user_id = message.from_user.id
    state = helpers.user_pages.get(user_id, {})

    if text.strip() == "/cancel":
        helpers.user_pages.pop(user_id, None)
        await message.answer("✅ Отменено", reply_markup=helpers.main_menu())
        return

    # Передаём текущее состояние в ИИ — он сам решит, что делать
    from ai.client import analyze_intent
    action, params = analyze_intent(user_id, text.strip(), reminder_state=state)

    if action == "cancel_reminder":
        helpers.user_pages.pop(user_id, None)
        await message.answer("✅ Отменено", reply_markup=helpers.main_menu())
        return

    if action == "set_reminder":
        text_v = (params.get("text") or state.get("text") or "").strip()
        time_v = (params.get("time") or state.get("time") or "").strip()
        date_v = (params.get("date") or state.get("date") or "").strip()
        need_clarification = params.get("need_clarification", False)
        question = params.get("question", "")

        # Обновляем состояние
        helpers.user_pages[user_id] = {
            "state": "waiting_reminder_clarification",
            "text": text_v,
            "time": time_v,
            "date": date_v,
            "question": question
        }

        if need_clarification and question:
            await message.answer(f"❓ {question}\n\n⏹ /cancel — отмена")
            return

        if text_v and time_v:
            full_time = _build_datetime(date_v, time_v)
            if full_time:
                add_reminder(user_id, text_v, full_time.isoformat())
                helpers.user_pages.pop(user_id, None)
                await message.answer(
                    f"⏰ Напоминание установлено!\n\n"
                    f"📝 {text_v}\n"
                    f"🕐 {full_time.strftime('%d.%m.%Y %H:%M')}"
                )
                return

    elif action == "chat":
        # ИИ понял, что это НЕ про напоминание — просто отвечаем
        helpers.user_pages.pop(user_id, None)
        from .text import generate_text
        await generate_text(message)
        return

    # Не поняли — повторяем вопрос
    q = state.get("question", "Уточни, пожалуйста.")
    await message.answer(f"❓ {q}\n\n⏹ /cancel — отмена")


async def list_reminders_msg(message: types.Message, user_id: int = None):
    if user_id is None:
        user_id = message.from_user.id
    reminders = get_user_reminders(user_id)
    if not reminders:
        await message.answer(
            "📭 У тебя пока нет напоминаний\n\n"
            "Напиши, например: «Напомни завтра в 10 купить хлеб»",
            reply_markup=no_reminders_kb()
        )
        return

    text = "⏰ Напоминания (ближайшие первыми):\n\n"
    for i, r in enumerate(reminders, 1):
        try:
            time_str = datetime.fromisoformat(r.get('time_local', r['time'])).strftime('%d.%m %H:%M')
        except Exception:
            time_str = r.get('time_local', r['time'])
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
            await message.answer("❌ Неверное время. Пример: /remind 10:00 Текст")
            return
        add_reminder(message.from_user.id, reminder_text, full_time.isoformat())
        await message.answer(
            f"⏰ Напоминание установлено!\n\n"
            f"📝 {reminder_text}\n"
            f"🕐 {full_time.strftime('%d.%m.%Y %H:%M')}"
        )
    except Exception:
        await message.answer("❌ Формат: /remind 10:00 Текст")


@router.message(Command("reminders"))
async def list_reminders_cmd(message: types.Message):
    await list_reminders_msg(message)


@router.callback_query(F.data == "my_reminders")
async def my_reminders_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    reminders = get_user_reminders(user_id)

    if not reminders:
        try:
            await callback.message.edit_text(
                "📭 У тебя пока нет напоминаний\n\n"
                "Напиши, например: «Напомни завтра в 10 купить хлеб»",
                reply_markup=no_reminders_kb()
            )
        except Exception:
            await callback.message.answer(
                "📭 У тебя пока нет напоминаний\n\n"
                "Напиши, например: «Напомни завтра в 10 купить хлеб»",
                reply_markup=no_reminders_kb()
            )
        await helpers.safe_answer(callback)
        return

    text = "⏰ Напоминания (ближайшие первыми):\n\n"
    for i, r in enumerate(reminders, 1):
        try:
            time_str = datetime.fromisoformat(r.get('time_local', r['time'])).strftime('%d.%m %H:%M')
        except Exception:
            time_str = r.get('time_local', r['time'])
        text += f"{i}. 🕐 {time_str} — {r['text']}\n"

    try:
        await callback.message.edit_text(text, reply_markup=reminders_kb(reminders))
    except Exception:
        await callback.message.answer(text, reply_markup=reminders_kb(reminders))
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
    await callback.message.edit_text(
        "🗑️ Все напоминания удалены",
        reply_markup=helpers.main_menu()
    )
    await helpers.safe_answer(callback)
