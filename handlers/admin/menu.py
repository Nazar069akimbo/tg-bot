from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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
    if not ADMIN_CODE:
        await message.answer("⛔ Вход отключён")
        return
    args = message.text.split()
    if len(args) > 1 and secrets.compare_digest(args[1], ADMIN_CODE):
        add_admin(message.from_user.id)
        await message.answer("✅ Вы админ!", reply_markup=admin_kb())
    else:
        logger.warning(f"⚠️ Неверный код от {message.from_user.id}")

@router.callback_query(F.data == "admin_panel")
async def admin_panel_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    await safe_edit(callback, "🛡️ <b>АДМИН-ПАНЕЛЬ</b>", admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_stats")
async def a_stats_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    total, total_tokens, premium_users = get_stats()
    today = get_users_count_today()
    week = get_users_count_week()
    avg_r, ratings_count = get_avg_rating()
    text = (f"📊 <b>СТАТИСТИКА</b>\n\n"
            f"👥 Всего: <b>{total}</b>\n🆕 Сегодня: {today}\n📅 За неделю: {week}\n"
            f"💎 Премиум: {premium_users}\n💰 Токенов: {total_tokens}\n⭐ Оценка: {avg_r} ({ratings_count})")
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn("admin_panel")]])
    await safe_edit(callback, text, kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_stars_balance")
async def a_stars_balance_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    
    balance = None
    try:
        if hasattr(callback.bot, "get_my_star_balance"):
            balance = await callback.bot.get_my_star_balance()
    except Exception:
        pass

    stars30, count30 = get_payments_summary(days=30)
    rub30 = stars30 * 0.45

    if balance is not None:
        rub_api = balance * 0.45
        api_line = f"💳 Баланс бота: <b>{balance} ⭐</b>
💵 ≈ {rub_api:.2f} ₽"
    else:
        api_line = (
            "🔌 API: <i>недоступен (нужна новая версия aiogram)</i>
"
            "💡 Точный баланс: @BotFather → /mybots → Stars"
        )

    text = (
        "⭐ <b>БАЛАНС STARS</b>

"
        f"{api_line}

"
        "📊 <b>За последние 30 дней</b>
"
        f"💰 Оплачено: <b>{stars30} ⭐</b>
"
        f"🧾 Платежей: <b>{count30}</b>
"
        f"💵 ≈ {rub30:.2f} ₽"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧾 Последние платежи", callback_data="a_payments_list")],
        [back_btn("admin_panel")]
    ])
    await safe_edit(callback, text, kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_payments_list")
async def a_payments_list_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    payments = get_payments_list(limit=20)
    if not payments:
        text = "🧾 <b>Платежи</b>\n\nПока нет ни одного платежа"
    else:
        text = "🧾 <b>Последние 20 платежей</b>\n\n"
        for p in payments:
            uid = p['user_id']
            uname = p.get('username') or ""
            link = helpers.user_link(uid, uname or str(uid))
            ts = p['timestamp'][:16].replace("T", " ")
            text += f"• {link} — <b>{p['stars_amount']} ⭐</b> ({p.get('plan', '?')})\n  <i>{ts}</i>\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn("a_stars_balance")]])
    await safe_edit(callback, text[:4000], kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_warnings")
async def a_warnings_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    warned = get_warned_users(limit=50)
    total_warns = sum(w['cnt'] for w in warned)
    text = f"⚠️ <b>ВАРНЫ</b>\n\n👥 Юзеров с варнами: <b>{len(warned)}</b>\n📊 Всего варнов: <b>{total_warns}</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn("admin_panel")]])
    await safe_edit(callback, text, kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_backup")
async def a_backup_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    await safe_edit(callback, "⏳ Бэкап...", None)
    try:
        from backup import GitHubBackup
        result = GitHubBackup().backup_all(reason='вручную')
        text = "✅ Готово!" if result else "⚠️ Частично (см. логи)"
    except Exception as e:
        text = f"❌ Ошибка: {str(e)[:150]}"
    await safe_edit(callback, text, admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_broadcast")
async def a_broadcast_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_broadcast"}
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn("admin_panel")]])
    await safe_edit(callback, "📢 <b>РАССЫЛКА</b>\n\nВведи текст.", kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_promocodes")
async def a_promocodes_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать", callback_data="a_create_promo")],
        [InlineKeyboardButton(text="📋 Список", callback_data="a_list_promos")],
        [back_btn("admin_panel")]
    ])
    await safe_edit(callback, "🎫 <b>ПРОМОКОДЫ</b>", kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_create_promo")
async def a_create_promo_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_promo_code"}
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn("a_promocodes", "🔙 Отмена")]])
    await safe_edit(callback, "🎫 Формат: <code>КОД | токены | дни</code>", kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_list_promos")
async def a_list_promos_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    promos = get_promocodes_list()
    text = "📋 <b>ПРОМОКОДЫ</b>\n\n"
    if not promos:
        text += "Пусто"
    else:
        for p in promos:
            text += f"🔹 <code>{p['code']}</code> +{p['bonus_tokens']}, {p['used']}/{p['max_uses']}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn("a_promocodes")]])
    await safe_edit(callback, text[:4000], kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_logs")
async def a_logs_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    import os
    size = os.path.getsize('logs/bot.log') if os.path.exists('logs/bot.log') else 0
    text = f"📜 <b>Логи</b>\n\n📁 logs/bot.log\n📦 Размер: {size / 1024:.1f} КБ"
    await safe_edit(callback, text, helpers.logs_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_logs_tail")
async def a_logs_tail_cb(callback: types.CallbackQuery):
    try:
        with open('logs/bot.log', 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()[-100:]
        content = "".join(lines).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        await safe_edit(callback, f"📄 <b>Последние 100 строк:</b>\n\n<pre>{content[-3800:]}</pre>", helpers.logs_kb())
    except Exception as e:
        await safe_edit(callback, f"❌ {e}", helpers.logs_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_logs_errors")
async def a_logs_errors_cb(callback: types.CallbackQuery):
    try:
        with open('logs/bot.log', 'r', encoding='utf-8', errors='ignore') as f:
            lines = [l for l in f.readlines() if "ERROR" in l][-100:]
        content = "".join(lines).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        await safe_edit(callback, f"❌ <b>Ошибки:</b>\n\n<pre>{content[-3800:]}</pre>", helpers.logs_kb())
    except Exception as e:
        await safe_edit(callback, f"❌ {e}", helpers.logs_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_logs_warnings")
async def a_logs_warnings_cb(callback: types.CallbackQuery):
    try:
        with open('logs/bot.log', 'r', encoding='utf-8', errors='ignore') as f:
            lines = [l for l in f.readlines() if "WARNING" in l][-100:]
        content = "".join(lines).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        await safe_edit(callback, f"⚠️ <b>Предупреждения:</b>\n\n<pre>{content[-3800:]}</pre>", helpers.logs_kb())
    except Exception as e:
        await safe_edit(callback, f"❌ {e}", helpers.logs_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_logs_download")
async def a_logs_download_cb(callback: types.CallbackQuery):
    if not os.path.exists('logs/bot.log'):
        await helpers.safe_answer(callback, "❌ Файл не найден", show_alert=True)
        return
    from aiogram.types import BufferedInputFile
    with open('logs/bot.log', 'rb') as f:
        data = f.read()
    await callback.message.answer_document(BufferedInputFile(data, filename="bot.log"), caption="📜 Логи")
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "noop")
async def noop_cb(callback: types.CallbackQuery):
    await helpers.safe_answer(callback)
