from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from .. import helpers
from .menu import back_btn, safe_edit

router = Router()
STAR_RATE = 2.0

def prices_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Пакеты", callback_data="a_prices|tokens")],
        [InlineKeyboardButton(text="💎 Подписки", callback_data="a_prices|premium")],
        [InlineKeyboardButton(text="➕ Добавить", callback_data="a_price_add|tokens")],
        [back_btn("admin_panel")]
    ])

@router.callback_query(F.data == "a_prices_menu")
async def a_prices_menu_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    await safe_edit(callback, "💰 <b>УПРАВЛЕНИЕ ЦЕНАМИ</b>", prices_menu_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("a_prices|"))
async def a_prices_list_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    kind = callback.data.split("|")[1]
    tariffs = get_all_tariffs(kind)
    title = "📦 <b>Пакеты</b>" if kind == "tokens" else "💎 <b>Подписки</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for t in tariffs:
        active = "✅" if t.get('active', 1) else "❌"
        label = f"{active} {t['name']} — {t['price_rub']}₽ / {t['tokens']}ток"
        if kind == "premium": label += f" / {t['days']}дн"
        kb.inline_keyboard.append([InlineKeyboardButton(text=label, callback_data=f"a_price_edit|{t['id']}")])
    kb.inline_keyboard.append([back_btn("a_prices_menu")])
    await safe_edit(callback, title, kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("a_price_edit|"))
async def a_price_edit_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    tid = int(callback.data.split("|")[1])
    t = get_tariff(tid)
    text = f"✏️ <b>{t['name']}</b>\n💰 {t['price_rub']}₽\n⭐ {t['stars']}\n🪙 {t['tokens']}\n👁 {'Вкл' if t.get('active', 1) else 'Выкл'}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить", callback_data=f"a_price_do_edit|{tid}")],
        [InlineKeyboardButton(text="🔄 Вкл/Выкл", callback_data=f"a_price_toggle|{tid}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"a_price_delete|{tid}")],
        [back_btn(f"a_prices|{t['kind']}")]
    ])
    await safe_edit(callback, text, kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("a_price_do_edit|"))
async def a_price_do_edit_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    tid = int(callback.data.split("|")[1])
    t = get_tariff(tid)
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_price_edit", "tariff_id": tid}
    fmt = "имя | цена_руб | токены | дни" if t['kind'] == "premium" else "имя | цена_руб | токены"
    await safe_edit(callback, f"Введи: <code>{fmt}</code>", InlineKeyboardMarkup(inline_keyboard=[[back_btn(f"a_price_edit|{tid}", "🔙 Отмена")]]))
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("a_price_toggle|"))
async def a_price_toggle_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    tid = int(callback.data.split("|")[1])
    t = get_tariff(tid)
    update_tariff(tid, active=0 if t.get('active', 1) else 1)
    await helpers.safe_answer(callback, "✅ Готово", show_alert=True)
    await a_price_edit_cb(callback)

@router.callback_query(F.data.startswith("a_price_delete|"))
async def a_price_delete_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    tid = int(callback.data.split("|")[1])
    t = get_tariff(tid)
    delete_tariff(tid)
    await helpers.safe_answer(callback, "🗑 Удалено", show_alert=True)
    cb2 = callback; cb2.data = f"a_prices|{t['kind']}"
    await a_prices_list_cb(cb2)

@router.callback_query(F.data.startswith("a_price_add|"))
async def a_price_add_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    kind = callback.data.split("|")[1]
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_price_add", "kind": kind}
    fmt = "имя | цена_руб | токены | дни" if kind == "premium" else "имя | цена_руб | токены"
    await safe_edit(callback, f"Введи: <code>{fmt}</code>", InlineKeyboardMarkup(inline_keyboard=[[back_btn("a_prices_menu", "🔙 Отмена")]]))
    await helpers.safe_answer(callback)
