from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from .. import helpers
from .menu import back_btn, safe_edit

router = Router()

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
    if not is_admin(callback.from_user.id): return
    await safe_edit(callback, "⚙️ <b>УПРАВЛЕНИЕ МОДЕЛЯМИ</b>", models_menu_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("a_models|"))
async def a_models_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    task = callback.data.split("|")[1]
    models = helpers.AVAILABLE_MODELS.get(task, [])
    title = "🎨 <b>Картинки</b>" if task == "image_generate" else "🧠 <b>Текст</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for mid, mname, cost, mplan in models:
        status = "❌ " if helpers.is_model_disabled(mid) else "✅ "
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{status}{mname} — {cost} ток.", callback_data=f"a_model_edit|{task}|{mid}")])
    kb.inline_keyboard.append([back_btn("a_models_menu")])
    await safe_edit(callback, title, kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("a_model_edit|"))
async def a_model_edit_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    parts = callback.data.split("|")
    task, mid = parts[1], parts[2]
    cost = helpers.MODEL_COSTS.get(mid, 0)
    name = helpers.MODEL_NAMES.get(mid, mid)
    disabled = helpers.is_model_disabled(mid)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить цену", callback_data=f"a_model_price|{task}|{mid}")],
        [InlineKeyboardButton(text="🟢 Включить" if disabled else "🔴 Отключить", callback_data=f"a_model_toggle|{task}|{mid}")],
        [back_btn(f"a_models|{task}")]
    ])
    status = "❌ Отключена" if disabled else "✅ Включена"
    text = f"⚙️ <b>{name}</b>\nЦена: <b>{cost}</b> токенов\nСтатус: <b>{status}</b>"
    await safe_edit(callback, text, kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("a_model_toggle|"))
async def a_model_toggle_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    parts = callback.data.split("|")
    task, mid = parts[1], parts[2]
    disabled = helpers.is_model_disabled(mid)
    new_state = "no" if disabled else "yes"
    set_setting(f"model_disabled_{mid}", new_state)
    await helpers.safe_answer(callback, f"✅ {'Включена' if new_state == 'no' else 'Отключена'}", show_alert=True)
    cb2 = callback; cb2.data = f"a_model_edit|{task}|{mid}"
    await a_model_edit_cb(cb2)

@router.callback_query(F.data.startswith("a_model_price|"))
async def a_model_price_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    parts = callback.data.split("|")
    task, mid = parts[1], parts[2]
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_model_price_edit", "model_id": mid}
    await safe_edit(callback, "✏️ Введи новую цену (число):", InlineKeyboardMarkup(inline_keyboard=[[back_btn(f"a_model_edit|{task}|{mid}", "🔙 Отмена")]]))
    await helpers.safe_answer(callback)

async def handle_model_price_edit(message: types.Message):
    user_id = message.from_user.id
    state = helpers.user_pages.get(user_id, {})
    mid = state.get("model_id")
    if message.text.strip() == "/cancel":
        helpers.user_pages.pop(user_id, None)
        from .menu import admin_kb
        await message.answer("✅ Отменено", reply_markup=admin_kb())
        return
    try:
        new_cost = int(message.text.strip())
        helpers.MODEL_COSTS[mid] = new_cost
        set_setting(f"model_cost_{mid}", str(new_cost))
        for task in ["text_chat", "image_generate"]:
            models = helpers.AVAILABLE_MODELS.get(task, [])
            for i, (m_id, m_name, c, p) in enumerate(models):
                if m_id == mid: models[i] = (m_id, m_name, new_cost, p)
        from .menu import admin_kb
        await message.answer(f"✅ Цена обновлена: <b>{new_cost}</b> токенов", reply_markup=admin_kb())
    except ValueError:
        await message.answer("❌ Нужно число.")
        return
    helpers.user_pages.pop(user_id, None)

@router.callback_query(F.data.startswith("a_models_stats|"))
async def a_models_stats_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    days = int(callback.data.split("|")[1])
    usage = get_model_usage(days=days, limit=20)
    text = f"📊 <b>За {days} дней</b>\n\n"
    if not usage: text += "Нет данных."
    else:
        for i, u in enumerate(usage, 1):
            text += f"{i}. {helpers.MODEL_NAMES.get(u['model'], u['model'])} — {u['cnt']} раз\n"
    await safe_edit(callback, text, InlineKeyboardMarkup(inline_keyboard=[[back_btn("a_models_menu")]]))
    await helpers.safe_answer(callback)
