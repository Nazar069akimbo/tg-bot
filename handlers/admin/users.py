from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from .. import helpers
from .menu import back_btn, safe_edit

router = Router()

def format_user_btn(u):
    status = "⛔" if u.get('is_blocked') else "✅"
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
    status = "Заблокирован ⛔" if user.get('is_blocked') else "Активен ✅"
    text = f"👤 <b>{link}</b>\n🆔 <code>{uid}</code>\n🪙 Токенов: {user['tokens']}\n📊 Статус: {status}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔓 Разблокировать" if user.get('is_blocked') else "🚫 Заблокировать",
            callback_data=f"a_user_toggle_block|{uid}"
        )],
        [InlineKeyboardButton(text="✍️ Написать сообщение", callback_data=f"a_user_write|{uid}")],
        [back_btn("a_search_users")]
    ])
    await safe_edit(callback, text, kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("a_user_toggle_block|"))
async def a_user_toggle_block_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    uid = int(callback.data.split("|")[1])
    user = get_user(uid)
    if user.get('is_blocked'):
        unblock_user(uid)
        await helpers.safe_answer(callback, "✅ Разблокирован", show_alert=True)
    else:
        block_user(uid)
        await helpers.safe_answer(callback, "✅ Заблокирован", show_alert=True)
    cb2 = callback
    cb2.data = f"a_user_manage|{uid}"
    await a_user_manage_cb(cb2)

@router.callback_query(F.data.startswith("a_user_write|"))
async def a_user_write_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    uid = int(callback.data.split("|")[1])
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_admin_reply_to_user", "target_user_id": uid}
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn("a_search_users", "🔙 Отмена")]])
    await safe_edit(callback, "✍️ Введи сообщение, которое отправишь юзеру:", kb)
    await helpers.safe_answer(callback)
