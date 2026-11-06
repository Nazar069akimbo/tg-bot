from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from .. import helpers
from .menu import back_btn, safe_edit

router = Router()
STAR_RATE = 2.0

def prices_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Пакеты токенов", callback_data="a_prices|tokens")],
        [InlineKeyboardButton(text="💎 Подписки", callback_data="a_prices|premium")],
        [InlineKeyboardButton(text="➕ Добавить пакет", callback_data="a_price_add|tokens")],
        [InlineKeyboardButton(text="➕ Добавить подписку", callback_data="a_price_add|premium")],
        [back_btn("admin_panel")]
    ])

@router.callback_query(F.data == "a_prices_menu")
async def a_prices_menu_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    tokens = get_all_tariffs("tokens")
    premium = get_all_tariffs("premium")
    text = (f"💰 <b>УПРАВЛЕНИЕ ЦЕНАМИ</b>\n\n"
            f"📦 Пакетов: <b>{len(tokens)}</b>\n💎 Подписок: <b>{len(premium)}</b>\n\n"
            f"Курс: <code>1⭐ ≈ {STAR_RATE}₽</code>")
    await safe_edit(callback, text, prices_menu_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("a_prices|"))
async def a_prices_list_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    kind = callback.data.split("|")[1]
    tariffs = get_all_tariffs(kind)
    title = "📦 <b>Пакеты токенов</b>" if kind == "tokens" else "💎 <b>Подписки</b>"
    text = f"{title}\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for t in tariffs:
        active = "✅" if t.get('active', 1) else "❌"
        if kind == "premium":
            label = f"{active} {t['name']} — {t['price_rub']}₽ / {t['days']}дн"
        else:
            label = f"{active} {t['name']} — {t['price_rub']}₽ / {t['tokens']}ток"
        kb.inline_keyboard.append([InlineKeyboardButton(text=label, callback_data=f"a_price_edit|{t['id']}")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="➕ Добавить", callback_data=f"a_price_add|{kind}")])
    kb.inline_keyboard.append([back_btn("a_prices_menu")])
    if not tariffs: text += "Пусто."
    await safe_edit(callback, text, kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("a_price_edit|"))
async def a_price_edit_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    tid = int(callback.data.split("|")[1])
    t = get_tariff(tid)
    if not t:
        await helpers.safe_answer(callback, "❌ Не найден", show_alert=True)
        return
    text = f"✏️ <b>{t['name']}</b>\n\n💰 {t['price_rub']}₽\n⭐ {t['stars']}\n🪙 {t['tokens']} токенов\n"
    if t['kind'] == "premium": text += f"📅 {t['days']} дней\n"
    text += f"👁 {'Активен' if t.get('active', 1) else 'Отключен'}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"a_price_do_edit|{tid}")],
        [InlineKeyboardButton(text="🔄 Вкл/Выкл", callback_data=f"a_price_toggle|{tid}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"a_price_delete|{tid}")],
        [back_btn(f"a_prices|{t['kind']}")]
    ])
    await safe_edit(callback, text, kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("a_price_do_edit|"))
async def a_price_do_edit_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    tid = int(callback.data.split("|")[1])
    t = get_tariff(tid)
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_price_edit", "tariff_id": tid}
    if t['kind'] == "premium":
        fmt = "имя | цена_руб | токены | дни"
        ex = f"{t['name']} | {t['price_rub']} | {t['tokens']} | {t['days']}"
    else:
        fmt = "имя | цена_руб | токены"
        ex = f"{t['name']} | {t['price_rub']} | {t['tokens']}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn(f"a_price_edit|{tid}", "🔙 Отмена")]])
    await safe_edit(callback, f"✏️ <b>Редактирование</b>\n\nФормат: <code>{fmt}</code>\nПример: <code>{ex}</code>", kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("a_price_toggle|"))
async def a_price_toggle_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    tid = int(callback.data.split("|")[1])
    t = get_tariff(tid)
    new_active = 0 if t.get('active', 1) else 1
    update_tariff(tid, active=new_active)
    await helpers.safe_answer(callback, f"✅ {'Включён' if new_active else 'Отключён'}", show_alert=True)
    await a_price_edit_cb(callback)

@router.callback_query(F.data.startswith("a_price_delete|"))
async def a_price_delete_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    tid = int(callback.data.split("|")[1])
    t = get_tariff(tid)
    kind = t['kind']
    delete_tariff(tid)
    await helpers.safe_answer(callback, f"🗑 Удалён: {t['name']}", show_alert=True)
    cb2 = callback
    cb2.data = f"a_prices|{kind}"
    await a_prices_list_cb(cb2)

@router.callback_query(F.data.startswith("a_price_add|"))
async def a_price_add_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    kind = callback.data.split("|")[1]
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_price_add", "kind": kind}
    if kind == "premium":
        fmt = "имя | цена_руб | токены | дни"
        ex = "Premium | 500 | 3000 | 30"
    else:
        fmt = "имя | цена_руб | токены"
        ex = "Новый пакет | 300 | 1500"
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn(f"a_prices|{kind}", "🔙 Отмена")]])
    await safe_edit(callback, f"➕ <b>Добавить</b>\n\nФормат: <code>{fmt}</code>\nПример: <code>{ex}</code>", kb)
    await helpers.safe_answer(callback)
