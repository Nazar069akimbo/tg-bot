from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from database.db import *
from .. import helpers
import os, secrets, logging

router = Router()
logger = logging.getLogger(__name__)

ADMIN_CODE = os.getenv("ADMIN_CODE")

def back_btn(target="admin_panel", text="🔙 Назад"):
    return InlineKeyboardButton(text=text, callback_data=target)

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="a_stats"),
         InlineKeyboardButton(text="⭐ Баланс Stars", callback_data="a_stars_balance")],
        [InlineKeyboardButton(text="🔍 Поиск юзера / Действия", callback_data="a_search_users"),
         InlineKeyboardButton(text="👥 Топ юзеров", callback_data="a_users")],
        [InlineKeyboardButton(text="💰 Управление ценами", callback_data="a_prices_menu"),
         InlineKeyboardButton(text="⚙️ Управление моделями", callback_data="a_models_menu")],
        [InlineKeyboardButton(text="📩 Тикеты", callback_data="a_support_tickets"),
         InlineKeyboardButton(text="⚠️ Варны", callback_data="a_warnings")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="a_broadcast"),
         InlineKeyboardButton(text="💾 Бэкап", callback_data="a_backup")],
        [InlineKeyboardButton(text="🎫 Промокоды", callback_data="a_promocodes"),
         InlineKeyboardButton(text="📜 Логи", callback_data="a_logs")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
    ])

async def safe_edit(callback, text, reply_markup=None):
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        try:
            await callback.message.answer(text, reply_markup=reply_markup)
        except Exception:
            pass

@router.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if is_admin(message.from_user.id):
        await message.answer("🛡️ <b>АДМИН-ПАНЕЛЬ</b>", reply_markup=admin_kb())
    else:
        await message.answer("🔐 Введи: /admin_code &lt;код&gt;")

@router.message(Command("admin_code"))
async def admin_code_cmd(message: types.Message):
    if not ADMIN_CODE: return
    args = message.text.split()
    if len(args) > 1 and secrets.compare_digest(args[1], ADMIN_CODE):
        add_admin(message.from_user.id)
        await message.answer("✅ Вы админ!", reply_markup=admin_kb())
    else:
        logger.warning(f"⚠️ Неверный код от {message.from_user.id}")

@router.callback_query(F.data == "admin_panel")
async def admin_panel_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    await safe_edit(callback, "🛡️ <b>АДМИН-ПАНЕЛЬ</b>", admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_stats")
async def a_stats_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    total, total_tokens, premium_users = get_stats()
    text = f"📊 <b>СТАТИСТИКА</b>\n\n👥 Всего: <b>{total}</b>\n💎 Премиум: {premium_users}\n💰 Токенов: {total_tokens}"
    await safe_edit(callback, text, InlineKeyboardMarkup(inline_keyboard=[[back_btn()]]))
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_stars_balance")
async def a_stars_balance_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    balance = None
    try:
        if hasattr(callback.bot, "get_my_star_balance"):
            balance = await callback.bot.get_my_star_balance()
    except Exception: pass
    
    stars30, count30 = get_payments_summary(days=30)
    api_line = f"💳 Баланс бота: <b>{balance} ⭐</b>" if balance is not None else "🔌 API: <i>недоступен</i>"
    text = f"⭐ <b>БАЛАНС STARS</b>\n\n{api_line}\n\n📊 За 30 дней: <b>{stars30} ⭐</b> ({count30} платежей)"
    await safe_edit(callback, text, InlineKeyboardMarkup(inline_keyboard=[[back_btn()]]))
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_backup")
async def a_backup_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    await safe_edit(callback, "⏳ Сохраняю...", None)
    from backup import GitHubBackup
    GitHubBackup().backup_all(reason='вручную')
    await safe_edit(callback, "✅ Бэкап создан!", admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_logs")
async def a_logs_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    size = os.path.getsize('logs/bot.log') if os.path.exists('logs/bot.log') else 0
    text = f"📜 <b>Логи</b>\n\nРазмер: {size/1024:.1f} КБ"
    await safe_edit(callback, text, InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📄 Последние 50", callback_data="a_logs_tail")], [back_btn()]]))
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_logs_tail")
async def a_logs_tail_cb(callback: types.CallbackQuery):
    with open('logs/bot.log', 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()[-50:]
    content = "".join(lines).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    await safe_edit(callback, f"<pre>{content[-3800:]}</pre>", InlineKeyboardMarkup(inline_keyboard=[[back_btn("a_logs")]]))
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_warnings")
async def a_warnings_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    warns = get_all_warnings(limit=20)
    text = "⚠️ <b>Последние варны</b>\n\n"
    if not warns: text += "Пусто."
    else:
        for w in warns:
            text += f"• <code>{w['user_id']}</code> — {w['reason']}\n"
    await safe_edit(callback, text, InlineKeyboardMarkup(inline_keyboard=[[back_btn()]]))
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_broadcast")
async def a_broadcast_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_broadcast"}
    await safe_edit(callback, "📢 Введи текст для рассылки:", InlineKeyboardMarkup(inline_keyboard=[[back_btn("admin_panel", "🔙 Отмена")]]))
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_promocodes")
async def a_promocodes_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать (КОД | токены | дни)", callback_data="a_create_promo")],
        [InlineKeyboardButton(text="📋 Список", callback_data="a_list_promos")],
        [back_btn()]
    ])
    await safe_edit(callback, "🎫 <b>ПРОМОКОДЫ</b>", kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_create_promo")
async def a_create_promo_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_promo_code"}
    await safe_edit(callback, "🎫 Введи: <code>КОД | токены | дни</code>", InlineKeyboardMarkup(inline_keyboard=[[back_btn("a_promocodes", "🔙 Отмена")]]))
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_list_promos")
async def a_list_promos_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    promos = get_promocodes_list()
    text = "📋 <b>ПРОМОКОДЫ</b>\n\n"
    if not promos: text += "Пусто"
    else:
        for p in promos:
            text += f"🔹 <code>{p['code']}</code> +{p['bonus_tokens']}, {p['used']}/{p['max_uses']}\n"
    await safe_edit(callback, text[:4000], InlineKeyboardMarkup(inline_keyboard=[[back_btn("a_promocodes")]]))
    await helpers.safe_answer(callback)
