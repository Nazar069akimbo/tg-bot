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
    """Понимает: 'HH:MM', 'через N минут', 'YYYY-MM-DD', 'today', 'tomorrow'."""
    now = datetime.now()
    today = now.date()

    if not time_str:
        return None

    time_str = str(time_str).strip().lower()
    date_str = str(date_str or "").strip().lower()

    # "через N минут/часов/дней"
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

    # "через 25" без единицы — минуты
    m = re.match(r'через\s+(\d+)$', time_str)
    if m:
        return now + timedelta(minutes=int(m.group(1)))

    # "HH:MM"
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


async def create_reminder_from_ai(message: types.Message, params: dict):
    user_id = message.from_user.id
    text = (params.get("text") or "").strip()
    time_str = (params.get("time") or "").strip()
    date_str = (params.get("date") or "").strip()
    need_clarification = params.get("need_clarification", False)
    question = params.get("question", "")

    if need_clarification or not text or not time_str:
        if not question:
            if not text:
                question = "Что напомнить?"
            elif not time_str:
                question = "Во сколько напомнить?"
            else:
                question = "Уточни, пожалуйста."

        helpers.user_pages[user_id] = {
            "state": "waiting_reminder_clarification",
            "text": text,
            "time": time_str,
            "date": date_str,
            "question": question
        }
        await message.answer(f"❓ {question}\n\n⏹ /cancel — отмена")
        return

    full_time = _build_datetime(date_str, time_str)
    if not full_time:
        await message.answer("❌ Не понял время. Напиши, например: «Напомни завтра в 10 купить хлеб»")
        return

    add_reminder(user_id, text, full_time.isoformat())
    await message.answer(
        f"⏰ **Напоминание установлено!**\n\n"
        f"📝 {text}\n"
        f"🕐 {full_time.strftime('%d.%m.%Y %H:%M')}"
    )
    logger.info(f"⏰ [{user_id}] {text} на {full_time}")


async def handle_clarification(message: types.Message, text: str):
    """Умный разбор ответа: что это — дата, время или текст."""
    user_id = message.from_user.id
    state = helpers.user_pages.get(user_id, {})

    if text.strip() == "/cancel":
        helpers.user_pages.pop(user_id, None)
        await message.answer("✅ Отменено", reply_markup=helpers.main_menu())
        return

    saved_text = state.get("text", "")
    saved_time = state.get("time", "")
    saved_date = state.get("date", "")
    question = state.get("question", "")

    # Спрашиваем ИИ, что это за ответ
    from ai.client import analyze_intent
    action, params = analyze_intent(user_id, text.strip())

    # Если ИИ вернул set_reminder — забираем оттуда поля
    if action == "set_reminder":
        new_text = (params.get("text") or "").strip()
        new_time = (params.get("time") or "").strip()
        new_date = (params.get("date") or "").strip()

        # Мержим: не перезаписываем то, что уже есть
        if new_text and not saved_text:
            saved_text = new_text
        if new_time:
            saved_time = new_time
        if new_date:
            saved_date = new_date

    else:
        # ИИ не понял как напоминание — пробуем парсить сами
        stripped = text.strip().lower()

        # Время: "18:03", "18 03", "6 вечера"
        m = re.search(r'(\d{1,2})[:.\s](\d{2})', stripped)
        if m and not saved_time:
            saved_time = f"{int(m.group(1)):02d}:{m.group(2)}"
        else:
            # Дата: "завтра", "сегодня", "25", "25.09"
            if stripped in ("завтра", "tomorrow"):
                saved_date = "tomorrow"
            elif stripped in ("сегодня", "today"):
                saved_date = "today"
            elif re.match(r'^\d{1,2}$', stripped) and not saved_date:
                # Число без месяца — считаем датой текущего месяца
                day = int(stripped)
                if 1 <= day <= 31:
                    now = datetime.now()
                    try:
                        saved_date = now.replace(day=day).strftime("%Y-%m-%d")
                    except ValueError:
                        saved_date = None
            elif re.match(r'^\d{1,2}\.\d{1,2}', stripped) and not saved_date:
                # "25.09" или "25.09.2026"
                parts = stripped.split(".")
                day = int(parts[0])
                month = int(parts[1]) if len(parts) > 1 else datetime.now().month
                year = int(parts[2]) if len(parts) > 2 else datetime.now().year
                try:
                    saved_date = f"{year:04d}-{month:02d}-{day:02d}"
                except Exception:
                    pass

        # Если это ответ на "Что напомнить?" — сохраняем как текст
        if "что напомнить" in question.lower() and not saved_text:
            saved_text = text.strip()

    # Пробуем завершить
    if saved_text and saved_time:
        full_time = _build_datetime(saved_date, saved_time)
        if full_time:
            add_reminder(user_id, saved_text, full_time.isoformat())
            helpers.user_pages.pop(user_id, None)
            await message.answer(
                f"⏰ **Напоминание установлено!**\n\n"
                f"📝 {saved_text}\n"
                f"🕐 {full_time.strftime('%d.%m.%Y %H:%M')}"
            )
            return

    # Что-то не хватает — спрашиваем ещё раз
    if not saved_text:
        new_question = "Что напомнить?"
    elif not saved_time:
        new_question = "Во сколько напомнить? (например, 18:03)"
    elif not saved_date:
        new_question = "На какой день? (сегодня, завтра или дата)"
    else:
        new_question = "Уточни, пожалуйста."

    helpers.user_pages[user_id] = {
        "state": "waiting_reminder_clarification",
        "text": saved_text,
        "time": saved_time,
        "date": saved_date,
        "question": new_question
    }
    await message.answer(f"❓ {new_question}\n\n⏹ /cancel — отмена")


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
            await message.answer("❌ Неверное время. Пример: /remind 10:00 Текст")
            return
        add_reminder(message.from_user.id, reminder_text, full_time.isoformat())
        await message.answer(
            f"⏰ **Напоминание установлено!**\n\n"
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
    await callback.message.edit_text("🗑️ Все напоминания удалены", reply_markup=helpers.main_menu())
    await helpers.safe_answer(callback)
