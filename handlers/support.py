from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from . import helpers
import os, logging
from datetime import datetime, timedelta

router = Router()
logger = logging.getLogger(__name__)

_admin_raw = os.getenv('ADMIN_ID')
ADMIN_ID = int(_admin_raw) if _admin_raw and _admin_raw.isdigit() else None

MAX_SUPPORT_LEN = 2000

def support_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 История", callback_data="support_history")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
    ])

def rating_kb(ticket_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐", callback_data=f"rate|{ticket_id}|1"),
            InlineKeyboardButton(text="⭐⭐", callback_data=f"rate|{ticket_id}|2"),
            InlineKeyboardButton(text="⭐⭐⭐", callback_data=f"rate|{ticket_id}|3"),
        ],
        [
            InlineKeyboardButton(text="⭐⭐⭐⭐", callback_data=f"rate|{ticket_id}|4"),
            InlineKeyboardButton(text="⭐⭐⭐⭐⭐", callback_data=f"rate|{ticket_id}|5"),
        ],
    ])

def support_kb_after_close():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Новый вопрос", callback_data="support")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
    ])

async def replace_message(callback: types.CallbackQuery, text: str, reply_markup=None):
    try:
        await callback.message.delete()
    except Exception:
        pass
    try:
        await callback.message.answer(text, reply_markup=reply_markup)
    except Exception as e:
        logger.warning(f"⚠️ replace_message: {e}")

def format_history(msgs: list) -> str:
    lines = []
    for m in msgs:
        sender = m.get("sender")
        if sender == "user":
            who = "👤 <b>Вы</b>"
        else:
            who = "🛡 <b>Поддержка</b>"
        txt = str(m.get("text", ""))
        txt = txt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        lines.append(f"{who}:\n{txt}")
    return "\n\n".join(lines)

@router.callback_query(F.data == "support")
async def support_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    profile = helpers.get_user_profile(user_id)
    if profile and profile.get("is_blocked"):
        await helpers.safe_answer(callback, "⛔ Вы заблокированы.", show_alert=True)
        return

    ticket = get_user_ticket(user_id)
    if ticket:
        msgs = get_ticket_messages(ticket['id'])
        text = f"💬 <b>Диалог с поддержкой</b> (тикет #{ticket['id']})\n\n"
        if msgs: text += format_history(msgs[-15:])
        else: text += "<i>Пока пусто.</i>"
        text += "\n\n✍️ Просто напиши следующее сообщение."
        helpers.user_pages[user_id] = {"state": "waiting_support_message", "ticket_id": ticket['id']}
        await replace_message(callback, text, support_kb())
    else:
        helpers.user_pages[user_id] = {"state": "waiting_support_message"}
        text = "💬 <b>Поддержка</b>\n\nНапиши свой вопрос."
        await replace_message(callback, text, support_kb())
    await helpers.safe_answer(callback)

@router.message(Command("support"))
async def support_cmd(message: types.Message):
    user_id = message.from_user.id
    profile = helpers.get_user_profile(user_id)
    if profile and profile.get("is_blocked"):
        await message.answer("⛔ Вы заблокированы.")
        return
    helpers.user_pages[user_id] = {"state": "waiting_support_message"}
    await message.answer("💬 <b>Поддержка</b>\n\nНапиши свой вопрос.", reply_markup=support_kb())

@router.callback_query(F.data == "support_history")
async def support_history_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    ticket = get_user_ticket(user_id)
    if not ticket:
        await helpers.safe_answer(callback, "Нет открытого тикета", show_alert=True)
        return
    msgs = get_ticket_messages(ticket['id'], limit=50)
    text = f"📜 <b>История тикета #{ticket['id']}</b>\n\n"
    text += format_history(msgs) if msgs else "<i>Пока нет сообщений</i>"
    await replace_message(callback, text, support_kb())
    await helpers.safe_answer(callback)

async def handle_support_message(message: types.Message):
    user_id = message.from_user.id
    text = (message.text or "").strip()[:MAX_SUPPORT_LEN]

    if text == "/cancel":
        helpers.user_pages.pop(user_id, None)
        await message.answer("✅ Отменено", reply_markup=helpers.main_menu())
        return

    if not text:
        await message.answer("❌ Отправь текст")
        return

    # Антиспам
    state = helpers.user_pages.get(user_id, {})
    now = datetime.now()
    last_msg = state.get("last_support_time")
    if last_msg:
        if now - last_msg < timedelta(seconds=3):
            await message.answer("⏳ Подожди 3 секунды.")
            return
        if now - last_msg < timedelta(seconds=30) and len(text) > 1000:
            add_warning(user_id, "Спам в поддержке", 0)
            count = get_warnings_count(user_id)
            if count >= 3:
                block_user(user_id)
                await message.answer("⛔ Вы заблокированы за спам.")
                return
            await message.answer("⚠️ Предупреждение за спам.")
            return
    state["last_support_time"] = now
    helpers.user_pages[user_id] = state

    safe_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    ticket = get_user_ticket(user_id)

    if not ticket:
        ticket_id = create_support_ticket(user_id, message.from_user.username or "", safe_text)
        user_link = helpers.user_link(user_id, message.from_user.full_name or str(user_id))
        notif = f"📩 <b>Новое обращение</b>\n👤 {user_link}\n🎫 Тикет #{ticket_id}\n\n💬 {safe_text}"
        await message.answer(f"✅ Сообщение отправлено (тикет #{ticket_id}).", reply_markup=helpers.main_menu())
    else:
        add_support_message(ticket['id'], 'user', safe_text)
        user_link = helpers.user_link(user_id, message.from_user.full_name or str(user_id))
        notif = f"💬 <b>Ответ в тикете #{ticket['id']}</b>\n👤 {user_link}\n\n💬 {safe_text}"
        await message.answer("✅ Отправлено.", reply_markup=helpers.main_menu())

    helpers.user_pages.pop(user_id, None)
    if ADMIN_ID:
        try:
            await message.bot.send_message(ADMIN_ID, notif)
        except Exception as e:
            logger.warning(f"⚠️ Не отправил админу: {e}")

@router.callback_query(F.data.startswith("reply_to_ticket|"))
async def reply_to_ticket_cb(callback: types.CallbackQuery):
    ticket_id = int(callback.data.split("|")[1])
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_support_message", "ticket_id": ticket_id}
    await callback.message.answer("✍️ Напиши свой ответ (это уйдёт в поддержку):")
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("rate|"))
async def rate_cb(callback: types.CallbackQuery):
    parts = callback.data.split("|")
    if len(parts) < 3: return
    try:
        ticket_id = int(parts[1])
        rating = int(parts[2])
    except ValueError: return
    if rating < 1 or rating > 5: return
    user_id = callback.from_user.id
    ticket = get_ticket(ticket_id)
    if not ticket or ticket['user_id'] != user_id:
        await helpers.safe_answer(callback, "❌ Тикет не найден", show_alert=True)
        return
    if get_ticket_rating(ticket_id):
        await helpers.safe_answer(callback, "✅ Ты уже оценил", show_alert=True)
        return
    save_ticket_rating(ticket_id, user_id, rating)
    await replace_message(callback, f"🙏 <b>Спасибо!</b> Оценка: {'⭐' * rating}", support_kb_after_close())
    await helpers.safe_answer(callback, "✅ Спасибо!")

async def notify_user_ticket_closed(bot, ticket_id: int, user_id: int):
    text = f"✅ <b>Тикет #{ticket_id} закрыт</b>\n\nПоставь оценку:"
    try:
        await bot.send_message(user_id, text, reply_markup=rating_kb(ticket_id))
    except Exception as e:
        logger.warning(f"⚠️ Не отправил юзеру: {e}")
