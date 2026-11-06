from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from .. import helpers
from .menu import back_btn, safe_edit
import logging

router = Router()
logger = logging.getLogger(__name__)

def models_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎨 Цены на картинки", callback_data="a_models|image_generate")],
        [InlineKeyboardButton(text="🧠 Цены на текст", callback_data="a_models|text_chat")],
        [InlineKeyboardButton(text="📊 Статистика (7 дней)", callback_data="a_models_stats|7")],
        [InlineKeyboardButton(text="📊 Статистика (30 дней)", callback_data="a_models_stats|30")],
        [back_btn("admin_panel")]
    ])

@router.callback_query(F.data == "a_models_menu")
async def a_models_menu_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    text = "⚙️ <b>УПРАВЛЕНИЕ МОДЕЛЯМИ</b>\n\n💰 Цены\n🔄 Вкл/Выкл\n📊 Статистика"
    await safe_edit(callback, text, models_menu_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("a_models|"))
async def a_models_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    task = callback.data.split("|")[1]
    models = helpers.AVAILABLE_MODELS.get(task, [])
    title = "🎨 <b>Цены на картинки</b>" if task == "image_generate" else "🧠 <b>Цены на текст</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for model_id, model_name, cost, min_plan in models:
        status = "❌ " if helpers.is_model_disabled(model_id) else "✅ "
        kb.inline_keyboard.append([InlineKeyboardButton(
            text=f"{status}{model_name} — {cost} ток.",
            callback_data=f"a_model_edit|{task}|{model_id}"
        )])
    kb.inline_keyboard.append([back_btn("a_models_menu")])
    await safe_edit(callback, title, kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("a_model_edit|"))
async def a_model_edit_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    parts = callback.data.split("|")
    task, model_id = parts[1], parts[2]
    current = helpers.MODEL_COSTS.get(model_id, 0)
    name = helpers.MODEL_NAMES.get(model_id, model_id)
    disabled = helpers.is_model_disabled(model_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить цену", callback_data=f"a_model_price|{task}|{model_id}")],
        [InlineKeyboardButton(
            text="🟢 Включить модель" if disabled else "🔴 Отключить модель",
            callback_data=f"a_model_toggle|{task}|{model_id}"
        )],
        [back_btn(f"a_models|{task}", "🔙 Отмена")]
    ])
    status = "❌ Отключена" if disabled else "✅ Включена"
    text = f"⚙️ <b>Модель: {name}</b>\n\nЦена: <b>{current}</b> токенов\nСтатус: <b>{status}</b>"
    await safe_edit(callback, text, kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("a_model_toggle|"))
async def a_model_toggle_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    parts = callback.data.split("|")
    task, model_id = parts[1], parts[2]
    disabled = helpers.is_model_disabled(model_id)
    new_state = "no" if disabled else "yes"
    set_setting(f"model_disabled_{model_id}", new_state)
    action = "включена" if new_state == "no" else "отключена"
    await helpers.safe_answer(callback, f"✅ Модель {action}", show_alert=True)
    cb2 = callback
    cb2.data = f"a_model_edit|{task}|{model_id}"
    await a_model_edit_cb(cb2)

@router.callback_query(F.data.startswith("a_model_price|"))
async def a_model_price_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    parts = callback.data.split("|")
    task, model_id = parts[1], parts[2]
    current = helpers.MODEL_COSTS.get(model_id, 0)
    name = helpers.MODEL_NAMES.get(model_id, model_id)
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_model_price_edit", "model_id": model_id}
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn(f"a_model_edit|{task}|{model_id}", "🔙 Отмена")]])
    await safe_edit(callback, f"✏️ <b>Цена: {name}</b>\n\nСейчас: <b>{current}</b> токенов.\nВведи новое число:", kb)
    await helpers.safe_answer(callback)

async def handle_model_price_edit(message: types.Message):
    user_id = message.from_user.id
    state = helpers.user_pages.get(user_id, {})
    model_id = state.get("model_id")
    text = message.text.strip()
    if text == "/cancel":
        helpers.user_pages.pop(user_id, None)
        from .menu import admin_kb
        await message.answer("✅ Отменено", reply_markup=admin_kb())
        return
    try:
        new_cost = int(text)
        if new_cost < 0: raise ValueError
    except ValueError:
        await message.answer("❌ Нужно целое число ≥ 0.")
        return
    helpers.MODEL_COSTS[model_id] = new_cost
    set_setting(f"model_cost_{model_id}", str(new_cost))
    for task in ["text_chat", "image_generate"]:
        models = helpers.AVAILABLE_MODELS.get(task, [])
        for i, (mid, mname, cost, mplan) in enumerate(models):
            if mid == model_id:
                models[i] = (mid, mname, new_cost, mplan)
    name = helpers.MODEL_NAMES.get(model_id, model_id)
    helpers.user_pages.pop(user_id, None)
    from .menu import admin_kb
    await message.answer(f"✅ <b>Цена обновлена</b>\n\n{name} → <b>{new_cost}</b> токенов", reply_markup=admin_kb())

@router.callback_query(F.data.startswith("a_models_stats|"))
async def a_models_stats_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    days = int(callback.data.split("|")[1])
    usage = get_model_usage(days=days, limit=20)
    total = get_model_usage_total(days=days)
    text = f"📊 <b>Статистика за {days} дней</b>\n\nВсего запросов: <b>{total}</b>\n\n"
    if not usage:
        text += "Пока нет данных."
    else:
        for i, u in enumerate(usage, 1):
            name = helpers.MODEL_NAMES.get(u['model'], u['model'])
            text += f"{i}. {name}\n     {u['cnt']} исп. · {u['total_cost'] or 0} токенов\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn("a_models_menu")]])
    await safe_edit(callback, text[:4000], kb)
    await helpers.safe_answer(callback)
