from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from .. import helpers
from .menu import back_btn, safe_edit
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "a_support_tickets")
async def a_support_tickets_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    tickets = get_support_tickets(status='open', limit=20)
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for t in tickets:
        name = t['username'] or str(t['user_id'])
        kb.inline_keyboard.append([InlineKeyboardButton(
            text=f"💬 #{t['id']} · {name}",
            callback_data=f"a_ticket_{t['id']}"
        )])
    kb.inline_keyboard.append([InlineKeyboardButton(text="📋 Закрытые", callback_data="a_closed_tickets")])
    kb.inline_keyboard.append([back_btn("admin_panel")])
    await safe_edit(callback, f"📩 <b>Открытые тикеты: {len(tickets)}</b>", kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_closed_tickets")
async def a_closed_tickets_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    tickets = get_support_tickets(status='closed', limit=20)
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for t in tickets:
        rating = get_ticket_rating(t['id'])
        r_str = f" {'⭐' * rating['rating']}" if rating else ""
        kb.inline_keyboard.append([InlineKeyboardButton(
            text=f"✅ #{t['id']} · {t['username'] or t['user_id']}{r_str}",
            callback_data=f"a_ticket_{t['id']}"
        )])
    kb.inline_keyboard.append([back_btn("a_support_tickets")])
    await safe_edit(callback, f"📋 <b>Закрытые тикеты: {len(tickets)}</b>", kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("a_ticket_"))
async def a_ticket_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    ticket_id = int(callback.data.replace("a_ticket_", ""))
    ticket = get_ticket(ticket_id)
    if not ticket:
        await helpers.safe_answer(callback, "❌ Тикет не найден", show_alert=True)
        return
    msgs = get_ticket_messages(ticket_id)
    user_link = helpers.user_link(ticket['user_id'], ticket['username'] or str(ticket['user_id']))
    text = f"💬 <b>Тикет #{ticket_id}</b> · <i>{ticket['status']}</i>\n👤 {user_link}\n🆔 <code>{ticket['user_id']}</code>\n\n"
    if msgs:
        for m in msgs[-15:]:
            who = "👤 <b>User</b>" if m['sender'] == 'user' else "🛡 <b>Admin</b>"
            safe_txt = str(m.get('text', '')).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            text += f"{who}: {safe_txt}\n\n"
    else:
        text += "<i>Пусто</i>"
    kb_rows = []
    if ticket['status'] == 'open':
        kb_rows.append([InlineKeyboardButton(text="✍️ Ответить", callback_data=f"a_reply_{ticket_id}")])
        kb_rows.append([InlineKeyboardButton(text="✅ Закрыть и запросить оценку", callback_data=f"a_close_{ticket_id}")])
    else:
        kb_rows.append([InlineKeyboardButton(text="♻️ Переоткрыть", callback_data=f"a_reopen_{ticket_id}")])
        rating = get_ticket_rating(ticket_id)
        if rating:
            kb_rows.append([InlineKeyboardButton(text=f"⭐ Оценка: {rating['rating']}/5", callback_data="noop")])
    kb_rows.append([InlineKeyboardButton(text="🗑 Удалить", callback_data=f"a_delete_ticket_{ticket_id}")])
    kb_rows.append([back_btn("a_support_tickets")])
    await safe_edit(callback, text[:4000], InlineKeyboardMarkup(inline_keyboard=kb_rows))
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("a_reply_"))
async def a_reply_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    ticket_id = int(callback.data.replace("a_reply_", ""))
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_admin_reply", "ticket_id": ticket_id}
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn(f"a_ticket_{ticket_id}", "🔙 Отмена")]])
    await safe_edit(callback, f"✍️ Напиши ответ для тикета #{ticket_id}:", kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("a_close_"))
async def a_close_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    ticket_id = int(callback.data.replace("a_close_", ""))
    ticket = get_ticket(ticket_id)
    if not ticket:
        await helpers.safe_answer(callback, "❌ Нет", show_alert=True)
        return
    close_ticket(ticket_id)
    try:
        from ..support import notify_user_ticket_closed
        await notify_user_ticket_closed(callback.bot, ticket_id, ticket['user_id'])
    except Exception as e:
        logger.warning(f"⚠️ Не отправил юзеру: {e}")
    await helpers.safe_answer(callback, "✅ Закрыт", show_alert=True)
    await a_support_tickets_cb(callback)

@router.callback_query(F.data.startswith("a_reopen_"))
async def a_reopen_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    ticket_id = int(callback.data.replace("a_reopen_", ""))
    reopen_ticket(ticket_id)
    await helpers.safe_answer(callback, "♻️ Переоткрыт", show_alert=True)
    await a_ticket_cb(callback)

@router.callback_query(F.data.startswith("a_delete_ticket_"))
async def a_delete_ticket_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    ticket_id = int(callback.data.replace("a_delete_ticket_", ""))
    delete_support_ticket(ticket_id)
    await helpers.safe_answer(callback, "🗑 Удалён", show_alert=True)
    await a_support_tickets_cb(callback)

@router.callback_query(F.data == "noop")
async def noop_cb(callback: types.CallbackQuery):
    await helpers.safe_answer(callback)

async def handle_admin_reply(message: types.Message):
    user_id = message.from_user.id
    state = helpers.user_pages.get(user_id, {})
    ticket_id = state.get("ticket_id")
    text = message.text.strip()[:2000]
    if text == "/cancel":
        helpers.user_pages.pop(user_id, None)
        from .menu import admin_kb
        await message.answer("✅ Отменено", reply_markup=admin_kb())
        return
    if not ticket_id:
        helpers.user_pages.pop(user_id, None)
        return
    safe_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    add_support_message(ticket_id, 'admin', safe_text)
    ticket = get_ticket(ticket_id)
    if ticket:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✍️ Ответить", callback_data=f"reply_to_ticket|{ticket_id}")]])
        try:
            await message.bot.send_message(
                ticket['user_id'],
                f"💬 <b>Ответ поддержки</b> (тикет #{ticket_id}):\n\n{safe_text}",
                reply_markup=kb
            )
        except Exception as e:
            logger.warning(f"⚠️ Не отправил юзеру: {e}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💬 Открыть тикет #{ticket_id}", callback_data=f"a_ticket_{ticket_id}")],
        [back_btn("a_support_tickets")]
    ])
    await message.answer(f"✅ Ответ отправлен в тикет #{ticket_id}", reply_markup=kb)
    helpers.user_pages.pop(user_id, None)
