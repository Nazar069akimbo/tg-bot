from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from .. import helpers
from .menu import back_btn, safe_edit
import logging

router = Router()
logger = logging.getLogger(__name__)

def backup_settings_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏱ Частота БД (Repsolver)", callback_data="a_bkp_db_freq")],
        [InlineKeyboardButton(text="📁 Частота папок юзеров", callback_data="a_bkp_users_freq")],
        [InlineKeyboardButton(text="🕒 Время ежедневного бэкапа", callback_data="a_bkp_time")],
        [InlineKeyboardButton(text="💾 Сделать бэкап сейчас", callback_data="a_bkp_now")],
        [back_btn("admin_panel")]
    ])

@router.callback_query(F.data == "a_backup_settings")
async def a_backup_settings_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    
    db_freq = int(get_setting("backup_db_freq") or "0")
    users_freq = int(get_setting("backup_users_freq") or "0")
    bkp_time = get_setting("backup_time") or "05:00"
    
    db_text = "Выключено" if db_freq == 0 else f"Каждые {db_freq} мин."
    users_text = "Выключено" if users_freq == 0 else f"Каждые {users_freq} мин."
    
    text = (
        "💾 <b>НАСТРОЙКИ БЭКАПА</b>\n\n"
        f"📦 <b>База данных:</b> {db_text}\n"
        f"👥 <b>Папки юзеров:</b> {users_text}\n"
        f"🕒 <b>Ежедневный бэкап:</b> {bkp_time}\n\n"
        "⚠️ <i>Внимание: частые бэкапы тратят трафик Render и лимиты GitHub!</i>"
    )
    await safe_edit(callback, text, backup_settings_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_bkp_db_freq")
async def a_bkp_db_freq_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⛔ Выключить", callback_data="a_bkp_db_set|0")],
        [InlineKeyboardButton(text="Каждые 5 мин", callback_data="a_bkp_db_set|5")],
        [InlineKeyboardButton(text="Каждые 15 мин", callback_data="a_bkp_db_set|15")],
        [InlineKeyboardButton(text="Каждые 60 мин", callback_data="a_bkp_db_set|60")],
        [back_btn("a_backup_settings")]
    ])
    await safe_edit(callback, "Выбери частоту бэкапа <b>Базы данных</b>:", kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("a_bkp_db_set|"))
async def a_bkp_db_set_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    freq = callback.data.split("|")[1]
    set_setting("backup_db_freq", freq)
    await helpers.safe_answer(callback, "✅ Сохранено", show_alert=True)
    await a_backup_settings_cb(callback)

@router.callback_query(F.data == "a_bkp_users_freq")
async def a_bkp_users_freq_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⛔ Выключить", callback_data="a_bkp_users_set|0")],
        [InlineKeyboardButton(text="Каждые 5 мин", callback_data="a_bkp_users_set|5")],
        [InlineKeyboardButton(text="Каждые 15 мин", callback_data="a_bkp_users_set|15")],
        [InlineKeyboardButton(text="Каждые 60 мин", callback_data="a_bkp_users_set|60")],
        [back_btn("a_backup_settings")]
    ])
    await safe_edit(callback, "Выбери частоту бэкапа <b>Папок юзеров</b>:", kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("a_bkp_users_set|"))
async def a_bkp_users_set_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    freq = callback.data.split("|")[1]
    set_setting("backup_users_freq", freq)
    await helpers.safe_answer(callback, "✅ Сохранено", show_alert=True)
    await a_backup_settings_cb(callback)

@router.callback_query(F.data == "a_bkp_time")
async def a_bkp_time_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_backup_time"}
    await safe_edit(callback, "🕒 Введи время для ежедневного бэкапа в формате <code>ЧЧ:ММ</code> (например, <code>05:00</code>):", InlineKeyboardMarkup(inline_keyboard=[[back_btn("a_backup_settings", "🔙 Отмена")]]))
    await helpers.safe_answer(callback)

async def handle_backup_time(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()
    if text == "/cancel":
        helpers.user_pages.pop(user_id, None)
        from .menu import admin_kb
        await message.answer("✅ Отменено", reply_markup=admin_kb())
        return
    try:
        h, m = text.split(":")
        if not (0 <= int(h) <= 23 and 0 <= int(m) <= 59): raise ValueError
        set_setting("backup_time", text)
        helpers.user_pages.pop(user_id, None)
        from .menu import admin_kb
        await message.answer(f"✅ Время ежедневного бэкапа установлено: <b>{text}</b>", reply_markup=admin_kb())
    except ValueError:
        await message.answer("❌ Неверный формат. Введи <code>ЧЧ:ММ</code> (например, 05:00).")

@router.callback_query(F.data == "a_bkp_now")
async def a_bkp_now_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    await helpers.safe_answer(callback, "⏳ Запускаю бэкап...", show_alert=True)
    from backup import GitHubBackup
    try:
        GitHubBackup().backup_all(reason='вручную из админки')
        await safe_edit(callback, "✅ Бэкап БД и папок юзеров успешно создан!", backup_settings_kb())
    except Exception as e:
        await safe_edit(callback, f"❌ Ошибка бэкапа: {e}", backup_settings_kb())
