from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from . import helpers
from datetime import datetime
import logging

router = Router()
logger = logging.getLogger(__name__)


def reminders_kb(reminders):
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for r in reminders:
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"❌ {r['text'][:25]}", callback_data=f"del_reminder_{r['id']}")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🗑️ Удалить все", callback_data="del_all_reminders")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")])
    return kb


def no_reminders_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]])


async def list_reminders_msg(message: types.Message, user_id: int = None):
    if user_id is None:
        user_id = message.from_user.id
    reminders = get_user_reminders(user_id)
    if not reminders:
        await message.answer("📭 Нет напоминаний\n\nНапиши, например: «Напомни завтра в 10 купить хлеб»", reply_markup=no_reminders_kb())
        return
    text = "⏰ Напоминания:\n\n"
    for i, r in enumerate(reminders, 1):
        try:
            ts = datetime.fromisoformat(r.get('time_local', r['time'])).strftime('%d.%m %H:%M')
        except Exception:
            ts = r.get('time_local', r['time'])
        text += f"{i}. 🕐 {ts} — {r['text']}\n"
    await message.answer(text, reply_markup=reminders_kb(reminders))


@router.message(Command("remind"))
async def set_reminder_cmd(message: types.Message):
    text = message.text.replace("/remind", "").strip()
    if not text:
        await message.answer("❌ Формат: /remind 10:00 Текст")
        return
    parts = text.split(" ", 1)
    if len(parts) < 2:
        await message.answer("❌ Формат: /remind 10:00 Текст")
        return
    full_time = helpers.build_reminder_time("today", parts[0])
    if not full_time:
        await message.answer("❌ Неверное время")
        return
    add_reminder(message.from_user.id, parts[1], full_time.isoformat())
    await message.answer(f"⏰ Установлено!\n\n📝 {parts[1]}\n🕐 {full_time.strftime('%d.%m.%Y %H:%M')}")


@router.message(Command("reminders"))
async def list_reminders_cmd(message: types.Message):
    await list_reminders_msg(message)


@router.callback_query(F.data == "my_reminders")
async def my_reminders_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    reminders = get_user_reminders(user_id)
    if not reminders:
        try:
            await callback.message.edit_text("📭 Нет напоминаний", reply_markup=no_reminders_kb())
        except Exception:
            await callback.message.answer("📭 Нет напоминаний", reply_markup=no_reminders_kb())
        await helpers.safe_answer(callback)
        return
    text = "⏰ Напоминания:\n\n"
    for i, r in enumerate(reminders, 1):
        try:
            ts = datetime.fromisoformat(r.get('time_local', r['time'])).strftime('%d.%m %H:%M')
        except Exception:
            ts = r.get('time_local', r['time'])
        text += f"{i}. 🕐 {ts} — {r['text']}\n"
    try:
        await callback.message.edit_text(text, reply_markup=reminders_kb(reminders))
    except Exception:
        await callback.message.answer(text, reply_markup=reminders_kb(reminders))
    await helpers.safe_answer(callback)


@router.callback_query(F.data.startswith("del_reminder_"))
async def del_reminder_cb(callback: types.CallbackQuery):
    try:
        rid = int(callback.data.replace("del_reminder_", ""))
    except ValueError:
        return
    delete_reminder(rid)
    await helpers.safe_answer(callback, "✅ Удалено", show_alert=True)
    await my_reminders_cb(callback)


@router.callback_query(F.data == "del_all_reminders")
async def del_all_reminders_cb(callback: types.CallbackQuery):
    delete_all_reminders(callback.from_user.id)
    await callback.message.edit_text("🗑️ Все удалены", reply_markup=helpers.main_menu())
    await helpers.safe_answer(callback)
