from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from .. import helpers
from .menu import back_btn, safe_edit
import logging

router = Router()
logger = logging.getLogger(__name__)

def format_user_btn(u):
    # Статусы: ⛔ (полный блок), 🔇 (репорт-блок), ✅ (активен)
    if u.get('is_blocked'):
        status = "⛔"
    elif u.get('is_soft_blocked'):
        status = "🔇"
    else:
        status = "✅"
    name = u['username'] or str(u['user_id'])
    return InlineKeyboardButton(
        text=f"{status} {name} (🪙{u['tokens']})",
        callback_data=f"a_user_manage|{u['user_id']}"
    )

@router.callback_query(F.data == "a_search_users")
async def a_search_users_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_user_search"}
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn("admin_panel")]])
    await safe_edit(callback, "🔍 <b>Поиск юзера</b>\n\nВведи имя, username или ID.\n\n⏹ /cancel — отмена", kb)
    await helpers.safe_answer(callback)

async def handle_user_search(message: types.Message):
    user_id = message.from_user.id
    query = message.text.strip()
    if query == "/cancel":
        helpers.user_pages.pop(user_id, None)
        from .menu import admin_kb
        await message.answer("✅ Отменено", reply_markup=admin_kb())
        return
    users = search_users(query=query, limit=10)
    if not users:
        await message.answer("❌ Ничего не найдено.")
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[])
        for u in users:
            kb.inline_keyboard.append([format_user_btn(u)])
        await message.answer(f"🔍 <b>Результаты: {query}</b>\n\nНажми на юзера:", reply_markup=kb)
    helpers.user_pages.pop(user_id, None)

@router.callback_query(F.data == "a_users")
async def a_users_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    users = search_users(limit=20)
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for u in users:
        kb.inline_keyboard.append([format_user_btn(u)])
    kb.inline_keyboard.append([back_btn("admin_panel")])
    await safe_edit(callback, "👥 <b>Топ по токенам</b>\n\nНажми на юзера:", kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("a_user_manage|"))
async def a_user_manage_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    uid = int(callback.data.split("|")[1])
    user = get_user(uid)
    if not user:
        await helpers.safe_answer(callback, "❌ Не найден", show_alert=True)
        return
    user = dict(user)
    name = user.get('username') or str(uid)
    link = helpers.user_link(uid, name)
    
    warn_cnt = get_warnings_count(uid)
    
    # Определяем статус
    if user.get('is_blocked'):
        status_text = "⛔ <b>ПОЛНАЯ БЛОКИРОВКА</b> (ничего не работает)"
        btn_hard = InlineKeyboardButton(text="🔓 Снять полную блокировку", callback_data=f"a_user_hard_unblock|{uid}")
    else:
        status_text = "✅ <b>Активен</b>"
        btn_hard = InlineKeyboardButton(text="⛔ Полная блокировка", callback_data=f"a_user_hard_block|{uid}")
        
    if user.get('is_soft_blocked') and not user.get('is_blocked'):
        status_text += "\n🔇 <b>Блокировка Репорт</b> (доступна только поддержка)"
        btn_soft = InlineKeyboardButton(text="🔓 Снять блок Репорт", callback_data=f"a_user_soft_unblock|{uid}")
    elif not user.get('is_blocked'):
        btn_soft = InlineKeyboardButton(text="🔇 Блокировка Репорт", callback_data=f"a_user_soft_block|{uid}")
    else:
        btn_soft = None
    
    text = (
        f"👤 <b>{link}</b>\n"
        f"🆔 <code>{uid}</code>\n"
        f"🪙 Токенов: {user['tokens']}\n\n"
        f"📊 Статус: {status_text}\n"
        f"⚠️ Варнов: <b>{warn_cnt}</b> / 3"
    )
    
    kb_rows = []
    kb_rows.append([btn_hard])
    if btn_soft:
        kb_rows.append([btn_soft])
    kb_rows.append([InlineKeyboardButton(text="⚠️ Выдать варн", callback_data=f"a_user_warn|{uid}")])
    kb_rows.append([InlineKeyboardButton(text="✍️ Написать сообщение", callback_data=f"a_user_write|{uid}")])
    kb_rows.append([back_btn("a_search_users")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await safe_edit(callback, text, kb)
    await helpers.safe_answer(callback)

# --- ПОЛНЫЙ БЛОК ---
@router.callback_query(F.data.startswith("a_user_hard_block|"))
async def a_user_hard_block_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    uid = int(callback.data.split("|")[1])
    block_user(uid)
    await helpers.safe_answer(callback, "⛔ Полностью заблокирован", show_alert=True)
    cb2 = callback
    cb2.data = f"a_user_manage|{uid}"
    await a_user_manage_cb(cb2)

@router.callback_query(F.data.startswith("a_user_hard_unblock|"))
async def a_user_hard_unblock_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    uid = int(callback.data.split("|")[1])
    unblock_user(uid)
    await helpers.safe_answer(callback, "✅ Полная блокировка снята", show_alert=True)
    cb2 = callback
    cb2.data = f"a_user_manage|{uid}"
    await a_user_manage_cb(cb2)

# --- РЕПОРТ БЛОК ---
@router.callback_query(F.data.startswith("a_user_soft_block|"))
async def a_user_soft_block_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    uid = int(callback.data.split("|")[1])
    soft_block_user(uid)
    await helpers.safe_answer(callback, "🔇 Блокировка Репорт включена", show_alert=True)
    cb2 = callback
    cb2.data = f"a_user_manage|{uid}"
    await a_user_manage_cb(cb2)

@router.callback_query(F.data.startswith("a_user_soft_unblock|"))
async def a_user_soft_unblock_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    uid = int(callback.data.split("|")[1])
    unsoft_block_user(uid)
    await helpers.safe_answer(callback, "✅ Блокировка Репорт снята", show_alert=True)
    cb2 = callback
    cb2.data = f"a_user_manage|{uid}"
    await a_user_manage_cb(cb2)

# --- ВАРН ---
@router.callback_query(F.data.startswith("a_user_warn|"))
async def a_user_warn_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    uid = int(callback.data.split("|")[1])
    add_warning(uid, "Нарушение правил", callback.from_user.id)
    warn_cnt = get_warnings_count(uid)
    
    if warn_cnt >= 3:
        block_user(uid)
        await helpers.safe_answer(callback, "⚠️ 3-й варн! Автоматическая ПОЛНАЯ блокировка.", show_alert=True)
    else:
        await helpers.safe_answer(callback, f"⚠️ Выдан варн. Всего: {warn_cnt}/3", show_alert=True)
        
    cb2 = callback
    cb2.data = f"a_user_manage|{uid}"
    await a_user_manage_cb(cb2)

@router.callback_query(F.data.startswith("a_user_write|"))
async def a_user_write_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    uid = int(callback.data.split("|")[1])
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_admin_reply_to_user", "target_user_id": uid}
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn("a_search_users", "🔙 Отмена")]])
    await safe_edit(callback, "✍️ Введи сообщение, которое отправишь юзеру:", kb)
    await helpers.safe_answer(callback)
