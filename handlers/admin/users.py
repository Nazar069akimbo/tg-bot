from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from .. import helpers
from .menu import back_btn, safe_edit
import logging

router = Router()
logger = logging.getLogger(__name__)

def format_user_btn(u):
    if u.get('is_blocked'): status = "⛔"
    elif u.get('is_soft_blocked'): status = "🔇"
    else: status = "✅"
    name = u['username'] or str(u['user_id'])
    return InlineKeyboardButton(text=f"{status} {name} (🪙{u['tokens']})", callback_data=f"a_user_manage|{u['user_id']}")

@router.callback_query(F.data == "a_search_users")
async def a_search_users_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_user_search"}
    await safe_edit(callback, "🔍 <b>Поиск юзера</b>\n\nВведи имя, username или ID.\n\n⏹ /cancel — отмена", InlineKeyboardMarkup(inline_keyboard=[[back_btn()]]))
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
        kb = InlineKeyboardMarkup(inline_keyboard=[[format_user_btn(u)] for u in users])
        await message.answer(f"🔍 <b>Результаты:</b>", reply_markup=kb)
    helpers.user_pages.pop(user_id, None)

@router.callback_query(F.data == "a_users")
async def a_users_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    users = search_users(limit=20)
    kb = InlineKeyboardMarkup(inline_keyboard=[[format_user_btn(u)] for u in users] + [[back_btn()]])
    await safe_edit(callback, "👥 <b>Топ по токенам</b>", kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("a_user_manage|"))
async def a_user_manage_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    uid = int(callback.data.split("|")[1])
    user = get_user(uid)
    if not user: return
    user = dict(user) # ВАЖНО: конвертация Row в dict
    
    warn_cnt = get_warnings_count(uid)
    link = helpers.user_link(uid, user.get('username') or str(uid))
    
    if user.get('is_blocked'):
        status, btn_hard = "⛔ <b>ПОЛНАЯ БЛОКИРОВКА</b>", InlineKeyboardButton(text="🔓 Снять полную", callback_data=f"a_user_hard_unblock|{uid}")
    else:
        status, btn_hard = "✅ <b>Активен</b>", InlineKeyboardButton(text="⛔ Полная блокировка", callback_data=f"a_user_hard_block|{uid}")
        
    if user.get('is_soft_blocked') and not user.get('is_blocked'):
        status += "\n🔇 <b>Блокировка Репорт</b>"
        btn_soft = InlineKeyboardButton(text="🔓 Снять репорт", callback_data=f"a_user_soft_unblock|{uid}")
    elif not user.get('is_blocked'):
        btn_soft = InlineKeyboardButton(text="🔇 Блокировка Репорт", callback_data=f"a_user_soft_block|{uid}")
    else:
        btn_soft = None
    
    text = f"👤 <b>{link}</b>\n🆔 <code>{uid}</code>\n🪙 Токенов: {user['tokens']}\n\n📊 Статус: {status}\n⚠️ Варнов: {warn_cnt}/3"
    
    kb = [[btn_hard]]
    if btn_soft: kb.append([btn_soft])
    kb.append([InlineKeyboardButton(text="⚠️ Выдать варн", callback_data=f"a_user_warn|{uid}")])
    kb.append([InlineKeyboardButton(text="✍️ Написать", callback_data=f"a_user_write|{uid}")])
    kb.append([back_btn("a_search_users")])
    
    await safe_edit(callback, text, InlineKeyboardMarkup(inline_keyboard=kb))
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("a_user_hard_block|"))
async def a_user_hard_block_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    uid = int(callback.data.split("|")[1])
    block_user(uid)
    await helpers.safe_answer(callback, "⛔ Заблокирован", show_alert=True)
    cb2 = callback; cb2.data = f"a_user_manage|{uid}"
    await a_user_manage_cb(cb2)

@router.callback_query(F.data.startswith("a_user_hard_unblock|"))
async def a_user_hard_unblock_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    uid = int(callback.data.split("|")[1])
    unblock_user(uid)
    await helpers.safe_answer(callback, "✅ Разблокирован", show_alert=True)
    cb2 = callback; cb2.data = f"a_user_manage|{uid}"
    await a_user_manage_cb(cb2)

@router.callback_query(F.data.startswith("a_user_soft_block|"))
async def a_user_soft_block_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    uid = int(callback.data.split("|")[1])
    soft_block_user(uid)
    await helpers.safe_answer(callback, "🔇 Репорт вкл", show_alert=True)
    cb2 = callback; cb2.data = f"a_user_manage|{uid}"
    await a_user_manage_cb(cb2)

@router.callback_query(F.data.startswith("a_user_soft_unblock|"))
async def a_user_soft_unblock_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    uid = int(callback.data.split("|")[1])
    unsoft_block_user(uid)
    await helpers.safe_answer(callback, "✅ Репорт снят", show_alert=True)
    cb2 = callback; cb2.data = f"a_user_manage|{uid}"
    await a_user_manage_cb(cb2)

@router.callback_query(F.data.startswith("a_user_warn|"))
async def a_user_warn_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    uid = int(callback.data.split("|")[1])
    add_warning(uid, "Нарушение", callback.from_user.id)
    warn_cnt = get_warnings_count(uid)
    if warn_cnt >= 3:
        block_user(uid)
        await helpers.safe_answer(callback, "⚠️ 3-й варн! Авто-блок.", show_alert=True)
    else:
        await helpers.safe_answer(callback, f"⚠️ Варн. Всего: {warn_cnt}/3", show_alert=True)
    cb2 = callback; cb2.data = f"a_user_manage|{uid}"
    await a_user_manage_cb(cb2)

@router.callback_query(F.data.startswith("a_user_write|"))
async def a_user_write_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    uid = int(callback.data.split("|")[1])
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_admin_reply_to_user", "target_user_id": uid}
    await safe_edit(callback, "✍️ Введи сообщение:", InlineKeyboardMarkup(inline_keyboard=[[back_btn("a_search_users", "🔙 Отмена")]]))
    await helpers.safe_answer(callback)
