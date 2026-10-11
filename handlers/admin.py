from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from . import helpers
from backup import GitHubBackup
import logging, os, asyncio
from datetime import datetime, timedelta

router = Router()
logger = logging.getLogger(__name__)
ADMIN_CODE = os.getenv("ADMIN_CODE", "30121979")
STAR_RATE = 2.0
LOG_PATH = 'logs/bot.log'


# ==================== ВСПОМОГАТЕЛЬНОЕ ====================

async def safe_edit(callback, text, reply_markup=None):
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        try:
            await callback.message.answer(text, reply_markup=reply_markup)
        except Exception:
            pass


def back_btn(target="admin_panel", text="🔙 Назад"):
    return InlineKeyboardButton(text=text, callback_data=target)


# ==================== ВХОД ====================

@router.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if is_admin(message.from_user.id):
        await message.answer("🛡️ <b>АДМИН-ПАНЕЛЬ</b>", reply_markup=helpers.admin_kb())
    else:
        await message.answer("🔐 /admin_code 30121979")


@router.message(Command("admin_code"))
async def admin_code_cmd(message: types.Message):
    args = message.text.split() if message.text else []
    if len(args) > 1 and args[1] == ADMIN_CODE:
        add_admin(message.from_user.id)
        await message.answer("✅ Вы админ!", reply_markup=helpers.admin_kb())


@router.callback_query(F.data == "admin_panel")
async def admin_panel_cb(callback: types.CallbackQuery):
    if is_admin(callback.from_user.id):
        await safe_edit(callback, "🛡️ <b>АДМИН-ПАНЕЛЬ</b>", helpers.admin_kb())


# ==================== СТАТИСТИКА ====================

@router.callback_query(F.data == "a_stats")
async def a_stats_cb(callback: types.CallbackQuery):
    total, total_tokens, premium_users = get_stats()
    today = get_users_count_today()
    week = get_users_count_week()
    avg_r, ratings_count = get_avg_rating()

    text = (
        "📊 <b>СТАТИСТИКА</b>\n\n"
        f"👥 Всего: <b>{total}</b>\n"
        f"🆕 Сегодня: {today}\n"
        f"📅 За неделю: {week}\n"
        f"💎 Премиум: {premium_users}\n"
        f"💰 Токенов: {total_tokens}\n"
        f"⭐ Средняя оценка: {avg_r} ({ratings_count} оценок)"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn("admin_panel")]])
    await safe_edit(callback, text, kb)
    await helpers.safe_answer(callback)


# ==================== БАЛАНС STARS ====================

@router.callback_query(F.data == "a_stars_balance")
async def a_stars_balance_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    balance = None
    err = None
    try:
        if hasattr(callback.bot, "get_my_star_balance"):
            balance = await callback.bot.get_my_star_balance()
    except Exception as e:
        err = str(e)

    stars30, count30 = get_payments_summary(days=30)
    rub30 = stars30 * 0.45

    if balance is None:
        api_line = f"🔌 API: <i>недоступен</i> ({err or 'нужен aiogram 3.7+'})"
    else:
        rub_api = balance * 0.45
        api_line = f"💳 Баланс бота: <b>{balance} ⭐</b>\n💵 ≈ {rub_api:.2f} ₽"

    text = (
        "⭐ <b>БАЛАНС STARS</b>\n\n"
        f"{api_line}\n\n"
        "📊 <b>За последние 30 дней</b>\n"
        f"💰 Оплачено: <b>{stars30} ⭐</b>\n"
        f"🧾 Платежей: <b>{count30}</b>\n"
        f"💵 ≈ {rub30:.2f} ₽\n\n"
        "💡 Точный баланс смотри в @BotFather → /mybots → Stars"
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


# ==================== УПРАВЛЕНИЕ ЦЕНАМИ ====================

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

    text = (
        "💰 <b>УПРАВЛЕНИЕ ЦЕНАМИ</b>\n\n"
        f"📦 Пакетов токенов: <b>{len(tokens)}</b>\n"
        f"💎 Подписок: <b>{len(premium)}</b>\n\n"
        "Курс: <code>1⭐ ≈ 2₽</code>\n"
        "Формат создания: <code>название | цена_руб | токены [| дни]</code>"
    )
    await safe_edit(callback, text, prices_menu_kb())
    await helpers.safe_answer(callback)


@router.callback_query(F.data.startswith("a_prices|"))
async def a_prices_list_cb(callback: types.CallbackQuery):
    kind = callback.data.split("|")[1]
    tariffs = get_all_tariffs(kind)

    title = "📦 <b>Пакеты токенов</b>" if kind == "tokens" else "💎 <b>Подписки</b>"
    text = f"{title}\n\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for t in tariffs:
        active = "✅" if t.get('active', 1) else "❌"
        if kind == "premium":
            label = f"{active} {t['name']} — {t['price_rub']}₽ / {t['stars']}⭐ / {t['days']}дн"
        else:
            label = f"{active} {t['name']} — {t['price_rub']}₽ / {t['stars']}⭐ / {t['tokens']}ток"
        kb.inline_keyboard.append([InlineKeyboardButton(text=label, callback_data=f"a_price_edit|{t['id']}")])

    kb.inline_keyboard.append([InlineKeyboardButton(text="➕ Добавить", callback_data=f"a_price_add|{kind}")])
    kb.inline_keyboard.append([back_btn("a_prices_menu")])

    if not tariffs:
        text += "Пусто. Нажми ➕ Добавить"

    await safe_edit(callback, text, kb)
    await helpers.safe_answer(callback)


@router.callback_query(F.data.startswith("a_price_edit|"))
async def a_price_edit_cb(callback: types.CallbackQuery):
    tid = int(callback.data.split("|")[1])
    t = get_tariff(tid)
    if not t:
        await helpers.safe_answer(callback, "❌ Тариф не найден", show_alert=True)
        return

    kind_label = "пакет" if t['kind'] == "tokens" else "подписка"

    text = (
        f"✏️ <b>{t['name']}</b> ({kind_label})\n\n"
        f"💰 Цена: <b>{t['price_rub']}₽</b>\n"
        f"⭐ Звёзд: <b>{t['stars']}</b>\n"
        f"🪙 Токенов: <b>{t['tokens']}</b>\n"
    )
    if t['kind'] == "premium":
        text += f"📅 Дней: <b>{t['days']}</b>\n"
    text += f"👁 Активен: <b>{'Да' if t.get('active', 1) else 'Нет'}</b>\n\n"

    if t['kind'] == "premium":
        text += f"<b>Формат редактирования:</b>\n<code>имя | цена_руб | токены | дни</code>"
    else:
        text += f"<b>Формат редактирования:</b>\n<code>имя | цена_руб | токены</code>"

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
    tid = int(callback.data.split("|")[1])
    t = get_tariff(tid)
    if not t:
        await helpers.safe_answer(callback, "❌ Тариф не найден", show_alert=True)
        return

    helpers.user_pages[callback.from_user.id] = {"state": "waiting_price_edit", "tariff_id": tid}

    if t['kind'] == "premium":
        fmt = "имя | цена_руб | токены | дни"
        example = f"{t['name']} | {t['price_rub']} | {t['tokens']} | {t['days']}"
    else:
        fmt = "имя | цена_руб | токены"
        example = f"{t['name']} | {t['price_rub']} | {t['tokens']}"

    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn(f"a_price_edit|{tid}", "🔙 Отмена")]])
    await safe_edit(callback,
        f"✏️ <b>Редактирование {t['name']}</b>\n\n"
        f"Формат: <code>{fmt}</code>\n\n"
        f"Пример: <code>{example}</code>\n\n"
        f"⏹ /cancel — отмена",
        kb
    )
    await helpers.safe_answer(callback)


@router.callback_query(F.data.startswith("a_price_toggle|"))
async def a_price_toggle_cb(callback: types.CallbackQuery):
    tid = int(callback.data.split("|")[1])
    t = get_tariff(tid)
    if not t:
        await helpers.safe_answer(callback, "❌ Нет", show_alert=True)
        return
    new_active = 0 if t.get('active', 1) else 1
    update_tariff(tid, active=new_active)
    await helpers.safe_answer(callback, f"✅ {'Включён' if new_active else 'Отключён'}", show_alert=True)
    await a_price_edit_cb(callback)


@router.callback_query(F.data.startswith("a_price_delete|"))
async def a_price_delete_cb(callback: types.CallbackQuery):
    tid = int(callback.data.split("|")[1])
    t = get_tariff(tid)
    if not t:
        await helpers.safe_answer(callback, "❌ Нет", show_alert=True)
        return
    kind = t['kind']
    delete_tariff(tid)
    await helpers.safe_answer(callback, f"🗑 Удалён: {t['name']}", show_alert=True)
    cb2 = callback
    cb2.data = f"a_prices|{kind}"
    await a_prices_list_cb(cb2)


@router.callback_query(F.data.startswith("a_price_add|"))
async def a_price_add_cb(callback: types.CallbackQuery):
    kind = callback.data.split("|")[1]
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_price_add", "kind": kind}

    if kind == "premium":
        fmt = "имя | цена_руб | токены | дни"
        ex = "Premium | 500 | 3000 | 30"
    else:
        fmt = "имя | цена_руб | токены"
        ex = "Новый пакет | 300 | 1500"

    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn(f"a_prices|{kind}", "🔙 Отмена")]])
    await safe_edit(callback,
        f"➕ <b>Добавить {'подписку' if kind == 'premium' else 'пакет'}</b>\n\n"
        f"Формат: <code>{fmt}</code>\n\n"
        f"Пример: <code>{ex}</code>\n\n"
        f"⭐ Звёзды считаются автоматически: <code>round(цена_руб / 2)</code>\n\n"
        f"⏹ /cancel — отмена",
        kb
    )
    await helpers.safe_answer(callback)


# ==================== ПОИСК ЮЗЕРОВ ====================

@router.callback_query(F.data == "a_search_users")
async def a_search_users_cb(callback: types.CallbackQuery):
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_user_search"}
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn("admin_panel")]])
    await safe_edit(callback,
        "🔍 <b>Поиск пользователей</b>\n\n"
        "Введи имя, username или ID.\n\n"
        "⏹ /cancel — отмена",
        kb
    )
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_filter_users")
async def a_filter_users_cb(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Только Премиум", callback_data="a_filter|premium")],
        [InlineKeyboardButton(text="👤 Только Базовые", callback_data="a_filter|basic")],
        [InlineKeyboardButton(text="🆕 Новые (7 дней)", callback_data="a_filter|recent")],
        [InlineKeyboardButton(text="💰 Токенов > 1000", callback_data="a_filter|rich")],
        [InlineKeyboardButton(text="💸 Токенов < 100", callback_data="a_filter|poor")],
        [back_btn("admin_panel")]
    ])
    await safe_edit(callback, "🎯 <b>Фильтры</b>\n\nВыбери:", kb)
    await helpers.safe_answer(callback)


@router.callback_query(F.data.startswith("a_filter|"))
async def a_filter_cb(callback: types.CallbackQuery):
    filter_type = callback.data.split("|")[1]
    users = search_users(filter_type=filter_type, limit=30)

    text = f"🎯 <b>Фильтр: {filter_type}</b>\n\n"
    for u in users:
        text += format_user_line(u)

    if not users:
        text += "Пусто."

    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn("a_filter_users")]])
    await safe_edit(callback, text[:4000], kb)
    await helpers.safe_answer(callback)


def format_user_line(u):
    """Строка юзера с кликабельным именем и ID."""
    uid = u['user_id']
    name = u.get('username') or "—"
    name_link = helpers.user_link(uid, name)
    status = "⛔" if u.get('is_blocked') else "✅"
    plan = "💎" if u.get('plan') in ('premium', 'premium_plus') else "👤"
    warn_cnt = get_warnings_count(uid)
    warn_str = f" ⚠️{warn_cnt}" if warn_cnt else ""
    return f"{status}{plan} {name_link}\n   🆔 <code>{uid}</code> · 🪙 {u['tokens']}{warn_str}\n\n"


async def handle_user_search(message: types.Message):
    user_id = message.from_user.id
    query = message.text.strip()

    if query == "/cancel":
        helpers.user_pages.pop(user_id, None)
        await message.answer("✅ Отменено", reply_markup=helpers.admin_kb())
        return

    users = search_users(query=query, limit=30)

    if not users:
        await message.answer(f"❌ Ничего не найдено по «{query}»", reply_markup=helpers.admin_kb())
    else:
        text = f"🔍 <b>Результаты: {query}</b>\n\n"
        for u in users:
            text += format_user_line(u)
        await message.answer(text[:4000], reply_markup=helpers.admin_kb())

    helpers.user_pages.pop(user_id, None)


# ==================== ТИКЕТЫ ====================

@router.callback_query(F.data == "a_support_tickets")
async def a_support_tickets_cb(callback: types.CallbackQuery):
    tickets = get_support_tickets(status='open', limit=20)

    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for t in tickets:
        name = t['username'] or str(t['user_id'])
        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"💬 #{t['id']} · {name}",
                callback_data=f"a_ticket_{t['id']}"
            )
        ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="✍️ Написать юзеру", callback_data="a_start_dialog")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="📋 История (закрытые)", callback_data="a_closed_tickets")])
    kb.inline_keyboard.append([back_btn("admin_panel")])

    await safe_edit(callback, f"📩 <b>Открытые тикеты: {len(tickets)}</b>\n\nВыбери:", kb)
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_closed_tickets")
async def a_closed_tickets_cb(callback: types.CallbackQuery):
    tickets = get_support_tickets(status='closed', limit=20)

    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for t in tickets:
        rating = get_ticket_rating(t['id'])
        r_str = f" {'⭐' * rating['rating']}" if rating else ""
        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"✅ #{t['id']} · {t['username'] or t['user_id']}{r_str}",
                callback_data=f"a_ticket_{t['id']}"
            )
        ])
    kb.inline_keyboard.append([back_btn("a_support_tickets")])

    await safe_edit(callback, f"📋 <b>Закрытые тикеты: {len(tickets)}</b>\n\nВыбери:", kb)
    await helpers.safe_answer(callback)


@router.callback_query(F.data.startswith("a_ticket_"))
async def a_ticket_cb(callback: types.CallbackQuery):
    ticket_id = int(callback.data.replace("a_ticket_", ""))
    ticket = get_ticket(ticket_id)
    if not ticket:
        await helpers.safe_answer(callback, "❌ Тикет не найден", show_alert=True)
        return

    msgs = get_ticket_messages(ticket_id)
    user_link = helpers.user_link(ticket['user_id'], ticket['username'] or str(ticket['user_id']))

    text = f"💬 <b>Тикет #{ticket_id}</b> · <i>{ticket['status']}</i>\n"
    text += f"👤 {user_link}\n"
    text += f"🆔 <code>{ticket['user_id']}</code>\n\n"

    if msgs:
        for m in msgs[-30:]:
            who = "👤 <b>User</b>" if m['sender'] == 'user' else "🛡 <b>Admin</b>"
            safe_txt = str(m.get('text', '')).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            text += f"{who}: {safe_txt}\n\n"
    else:
        text += "<i>Пусто</i>"

    kb_rows = []
    if ticket['status'] == 'open':
        kb_rows.append([InlineKeyboardButton(text="✍️ Ответить", callback_data=f"a_reply_{ticket_id}")])
        kb_rows.append([InlineKeyboardButton(text="✅ Закрыть и запросить оценку", callback_data=f"a_close_{ticket_id}")])
    else:
        kb_rows.append([InlineKeyboardButton(text="♻️ Переоткрыть", callback_data=f"a_reopen_{ticket_id}")])
        rating = get_ticket_rating(ticket_id)
        if rating:
            kb_rows.append([InlineKeyboardButton(
                text=f"⭐ Оценка: {'⭐' * rating['rating']} ({rating['rating']}/5)",
                callback_data="noop"
            )])

    kb_rows.append([InlineKeyboardButton(text="🗑 Удалить тикет", callback_data=f"a_delete_ticket_{ticket_id}")])
    kb_rows.append([back_btn("a_support_tickets")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await safe_edit(callback, text[:4000], kb)
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "noop")
async def noop_cb(callback: types.CallbackQuery):
    await helpers.safe_answer(callback)


@router.callback_query(F.data.startswith("a_reply_"))
async def a_reply_cb(callback: types.CallbackQuery):
    ticket_id = int(callback.data.replace("a_reply_", ""))
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_admin_reply", "ticket_id": ticket_id}
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn(f"a_ticket_{ticket_id}", "🔙 Отмена")]])
    await safe_edit(callback, f"✍️ Напиши ответ для тикета #{ticket_id}:", kb)
    await helpers.safe_answer(callback)


@router.callback_query(F.data.startswith("a_close_"))
async def a_close_cb(callback: types.CallbackQuery):
    ticket_id = int(callback.data.replace("a_close_", ""))
    ticket = get_ticket(ticket_id)
    if not ticket:
        await helpers.safe_answer(callback, "❌ Нет", show_alert=True)
        return

    close_ticket(ticket_id)

    try:
        from .support import notify_user_ticket_closed
        await notify_user_ticket_closed(callback.bot, ticket_id, ticket['user_id'])
    except Exception as e:
        logger.warning(f"⚠️ Не отправил юзеру: {e}")

    await helpers.safe_answer(callback, "✅ Тикет закрыт, юзеру отправлен запрос оценки", show_alert=True)
    await a_support_tickets_cb(callback)


@router.callback_query(F.data.startswith("a_reopen_"))
async def a_reopen_cb(callback: types.CallbackQuery):
    ticket_id = int(callback.data.replace("a_reopen_", ""))
    reopen_ticket(ticket_id)
    await helpers.safe_answer(callback, "♻️ Тикет переоткрыт", show_alert=True)
    await a_ticket_cb(callback)


@router.callback_query(F.data.startswith("a_delete_ticket_"))
async def a_delete_ticket_cb(callback: types.CallbackQuery):
    ticket_id = int(callback.data.replace("a_delete_ticket_", ""))
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM support_messages WHERE ticket_id = ?", (ticket_id,))
        cursor.execute("DELETE FROM support_tickets WHERE id = ?", (ticket_id,))
        cursor.execute("DELETE FROM ticket_ratings WHERE ticket_id = ?", (ticket_id,))
    await helpers.safe_answer(callback, "🗑 Удалён", show_alert=True)
    await a_support_tickets_cb(callback)


# ==================== НАЧАТЬ ДИАЛОГ ПЕРВЫМ ====================

@router.callback_query(F.data == "a_start_dialog")
async def a_start_dialog_cb(callback: types.CallbackQuery):
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_start_dialog_user"}
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn("a_support_tickets", "🔙 Отмена")]])
    await safe_edit(callback,
        "✍️ <b>Начать диалог первым</b>\n\n"
        "Введи ID юзера, которому хочешь написать.\n"
        "Бот создаст тикет и отправит сообщение от твоего имени.\n\n"
        "⏹ /cancel — отмена",
        kb
    )
    await helpers.safe_answer(callback)


async def handle_start_dialog(message: types.Message, admin_id: int):
    text = message.text.strip()

    if text == "/cancel":
        helpers.user_pages.pop(admin_id, None)
        await message.answer("✅ Отменено", reply_markup=helpers.admin_kb())
        return

    try:
        target_id = int(text)
    except ValueError:
        await message.answer("❌ Нужно число (ID). Попробуй снова или /cancel")
        return

    user = get_user(target_id)
    if not user:
        await message.answer(f"❌ Юзер {target_id} не найден. Пусть напишет /start.", reply_markup=helpers.admin_kb())
        helpers.user_pages.pop(admin_id, None)
        return

    ticket_id = create_support_ticket(target_id, user['username'] or "", None)

    helpers.user_pages[admin_id] = {"state": "waiting_admin_reply", "ticket_id": ticket_id}

    await message.answer(
        f"✅ Тикет #{ticket_id} создан для {helpers.user_link(target_id, user['username'] or str(target_id))}\n\n"
        f"✍️ Напиши первое сообщение:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_btn(f"a_ticket_{ticket_id}", "🔙 Отмена")]])
    )


# ==================== ОТВЕТ АДМИНА ====================

async def handle_admin_reply(message: types.Message):
    user_id = message.from_user.id
    state = helpers.user_pages.get(user_id, {})
    ticket_id = state.get("ticket_id")
    text = message.text.strip()

    if text == "/cancel":
        helpers.user_pages.pop(user_id, None)
        await message.answer("✅ Отменено", reply_markup=helpers.admin_kb())
        return

    if not ticket_id:
        helpers.user_pages.pop(user_id, None)
        return

    safe_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    add_support_message(ticket_id, 'admin', safe_text)

    ticket = get_ticket(ticket_id)
    if ticket:
        try:
            await message.bot.send_message(
                ticket['user_id'],
                f"💬 <b>Ответ поддержки</b> (тикет #{ticket_id}):\n\n{safe_text}\n\n"
                f"<i>Можешь ответить прямо здесь.</i>"
            )
        except Exception as e:
            logger.warning(f"⚠️ Не отправил юзеру: {e}")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💬 Открыть тикет #{ticket_id}", callback_data=f"a_ticket_{ticket_id}")],
        [back_btn("a_support_tickets")]
    ])
    await message.answer(f"✅ Ответ отправлен в тикет #{ticket_id}", reply_markup=kb)
    helpers.user_pages.pop(user_id, None)


# ==================== ПОЛЬЗОВАТЕЛИ (список) ====================

@router.callback_query(F.data == "a_users")
async def a_users_cb(callback: types.CallbackQuery):
    users = search_users(limit=50)
    text = "👥 <b>Топ по токенам</b>\n\n"
    for u in users:
        text += format_user_line(u)
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn("admin_panel")]])
    await safe_edit(callback, text[:4000], kb)
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_give_tokens")
async def a_give_tokens_cb(callback: types.CallbackQuery):
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_give_tokens"}
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn("admin_panel")]])
    await safe_edit(callback, "⭐ <b>РАЗДАТЬ ТОКЕНЫ</b>\n\nФормат: <code>ID | кол-во</code>", kb)
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_broadcast")
async def a_broadcast_cb(callback: types.CallbackQuery):
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_broadcast"}
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn("admin_panel")]])
    await safe_edit(callback, "📢 <b>РАССЫЛКА</b>\n\nВведи текст.", kb)
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_block")
async def a_block_cb(callback: types.CallbackQuery):
    users = search_users(limit=30)
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for u in users:
        name = u['username'] or str(u['user_id'])
        status = "✅" if u['is_blocked'] == 0 else "⛔"
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{status} {name}", callback_data=f"block_user_{u['user_id']}")])
    kb.inline_keyboard.append([back_btn("admin_panel")])
    await safe_edit(callback, "🚫 <b>БЛОКИРОВКА</b>", kb)
    await helpers.safe_answer(callback)


@router.callback_query(F.data.startswith("block_user_"))
async def block_user_action(callback: types.CallbackQuery):
    uid = int(callback.data.replace("block_user_", ""))
    user = get_user(uid)
    if user['is_blocked'] == 1:
        unblock_user(uid)
    else:
        block_user(uid)
    await helpers.safe_answer(callback, "✅ Готово", show_alert=True)
    await a_block_cb(callback)


# ==================== ВАРНЫ ====================

def warnings_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список варновых", callback_data="a_warn_list")],
        [InlineKeyboardButton(text="📜 Все варны", callback_data="a_warn_all")],
        [InlineKeyboardButton(text="➕ Выдать варн", callback_data="a_warn_add")],
        [InlineKeyboardButton(text="➖ Снять варн", callback_data="a_warn_remove")],
        [back_btn("admin_panel")]
    ])


@router.callback_query(F.data == "a_warnings")
async def a_warnings_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    warned = get_warned_users(limit=50)
    total_warns = sum(w['cnt'] for w in warned)
    text = (
        "⚠️ <b>ВАРНЫ</b>\n\n"
        f"👥 Юзеров с варнами: <b>{len(warned)}</b>\n"
        f"📊 Всего варнов: <b>{total_warns}</b>"
    )
    await safe_edit(callback, text, warnings_menu_kb())
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_warn_list")
async def a_warn_list_cb(callback: types.CallbackQuery):
    warned = get_warned_users(limit=50)
    if not warned:
        text = "📋 <b>Список варновых</b>\n\nПусто"
    else:
        text = "📋 <b>Список варновых</b>\n\n"
        for w in warned:
            user = get_user(w['user_id'])
            uname = user['username'] if user else ""
            link = helpers.user_link(w['user_id'], uname or str(w['user_id']))
            text += f"• {link} · 🆔 <code>{w['user_id']}</code> — <b>{w['cnt']}</b> ⚠️\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn("a_warnings")]])
    await safe_edit(callback, text[:4000], kb)
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_warn_all")
async def a_warn_all_cb(callback: types.CallbackQuery):
    warns = get_all_warnings(limit=50)
    if not warns:
        text = "📜 <b>Все варны</b>\n\nПусто"
    else:
        text = "📜 <b>Последние 50 варнов</b>\n\n"
        for w in warns:
            user = get_user(w['user_id'])
            uname = user['username'] if user else ""
            link = helpers.user_link(w['user_id'], uname or str(w['user_id']))
            ts = w['created_at'][:16].replace("T", " ")
            reason = str(w.get('reason', '—'))[:40]
            text += f"• {link} · <i>{ts}</i>\n  {reason}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn("a_warnings")]])
    await safe_edit(callback, text[:4000], kb)
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_warn_add")
async def a_warn_add_cb(callback: types.CallbackQuery):
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_warn_add"}
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn("a_warnings", "🔙 Отмена")]])
    await safe_edit(callback,
        "➕ <b>Выдать варн</b>\n\n"
        "Формат: <code>ID | причина</code>\n"
        "Пример: <code>6957852385 | спам в чате</code>",
        kb
    )
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_warn_remove")
async def a_warn_remove_cb(callback: types.CallbackQuery):
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_warn_remove"}
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn("a_warnings", "🔙 Отмена")]])
    await safe_edit(callback, "➖ <b>Снять варн</b>\n\nВведи ID юзера — снимутся все варны.", kb)
    await helpers.safe_answer(callback)


async def handle_warn_add(message: types.Message, admin_id: int):
    text = message.text.strip()
    if text == "/cancel":
        helpers.user_pages.pop(admin_id, None)
        await message.answer("✅ Отменено", reply_markup=helpers.admin_kb())
        return

    parts = text.split("|", 1)
    if len(parts) < 2:
        await message.answer("❌ Формат: <code>ID | причина</code>")
        return

    try:
        target_id = int(parts[0].strip())
    except ValueError:
        await message.answer("❌ ID должен быть числом")
        return

    reason = parts[1].strip()[:200]
    user = get_user(target_id)
    if not user:
        await message.answer(f"❌ Юзер {target_id} не найден в БД.")
        return

    add_warning(target_id, reason, admin_id)
    count = get_warnings_count(target_id)
    link = helpers.user_link(target_id, user['username'] or str(target_id))

    try:
        await message.bot.send_message(
            target_id,
            f"⚠️ <b>Вам выдан варн</b>\n\n"
            f"📝 Причина: {reason}\n"
            f"📊 Всего варнов: <b>{count}</b>\n\n"
            f"При 3 варнах аккаунт может быть заблокирован."
        )
    except Exception as e:
        logger.warning(f"⚠️ Не отправил варн юзеру: {e}")

    await message.answer(f"✅ Варн выдан {link}\n📊 Всего: <b>{count}</b>", reply_markup=helpers.admin_kb())
    helpers.user_pages.pop(admin_id, None)


async def handle_warn_remove(message: types.Message, admin_id: int):
    text = message.text.strip()
    if text == "/cancel":
        helpers.user_pages.pop(admin_id, None)
        await message.answer("✅ Отменено", reply_markup=helpers.admin_kb())
        return

    try:
        target_id = int(text)
    except ValueError:
        await message.answer("❌ ID должен быть числом")
        return

    count_before = get_warnings_count(target_id)
    remove_all_warnings(target_id)

    user = get_user(target_id)
    link = helpers.user_link(target_id, (user['username'] if user else None) or str(target_id))

    await message.answer(f"✅ Снято варнов: <b>{count_before}</b> у {link}", reply_markup=helpers.admin_kb())
    helpers.user_pages.pop(admin_id, None)


# ==================== БЭКАП / ВОССТАНОВЛЕНИЕ ====================

@router.callback_query(F.data == "a_backup")
async def a_backup_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    await safe_edit(callback, "⏳ Бэкап...", None)
    try:
        bk = GitHubBackup()
        if hasattr(bk, "backup_all"):
            result = bk.backup_all(reason='вручную')
        else:
            db_ok = bk.backup_db(reason='вручную')
            users_ok = bk.backup_users(reason='вручную')
            result = db_ok and users_ok
        text = "✅ Готово!" if result else "⚠️ Частично (см. логи)"
    except Exception as e:
        logger.error(f"❌ Бэкап: {e}")
        text = f"❌ Ошибка: {str(e)[:150]}"
    await safe_edit(callback, text, helpers.admin_kb())
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_export_db")
async def export_db_cb(callback: types.CallbackQuery):
    if not os.path.exists('data/repsolver.db'):
        await helpers.safe_answer(callback, "❌ Нет БД", show_alert=True)
        return
    await callback.message.answer_document(
        BufferedInputFile(open('data/repsolver.db', 'rb').read(), filename="repsolver.db"),
        caption="📁 БД", reply_markup=helpers.admin_kb()
    )
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_restore_github")
async def restore_github_cb(callback: types.CallbackQuery):
    await safe_edit(callback, "⏳ Восстанавливаю БД...", None)
    result = GitHubBackup().restore_latest_backup()
    if result:
        from database.db import reload_db_connection
        reload_db_connection()
        await safe_edit(callback, "✅ БД восстановлена!", helpers.admin_kb())
    else:
        await safe_edit(callback, "❌ Ошибка", helpers.admin_kb())
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_restore_users")
async def restore_users_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    await safe_edit(callback, "⏳ Восстанавливаю...\n\n1/2: папки из GitHub", None)
    try:
        ok_users = GitHubBackup().restore_users()
    except Exception as e:
        logger.error(f"❌ restore_users: {e}")
        ok_users = False

    await safe_edit(callback, "⏳ Восстанавливаю...\n\n2/2: токены в БД", None)
    try:
        from database.db import restore_from_user_folders
        count = restore_from_user_folders()
    except Exception as e:
        logger.error(f"❌ restore_from_user_folders: {e}")
        count = 0

    text = (
        f"✅ <b>Восстановление готово</b>\n\n"
        f"📁 Папки: {'скачаны' if ok_users else 'пусто/ошибка'}\n"
        f"💾 Токены в БД: обновлено <b>{count}</b> пользователей"
    )
    await safe_edit(callback, text, helpers.admin_kb())
    await helpers.safe_answer(callback)


# ==================== ПРОМОКОДЫ ====================

@router.callback_query(F.data == "a_promocodes")
async def a_promocodes_cb(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать", callback_data="a_create_promo")],
        [InlineKeyboardButton(text="📋 Список", callback_data="a_list_promos")],
        [back_btn("admin_panel")]
    ])
    await safe_edit(callback, "🎫 <b>ПРОМОКОДЫ</b>", kb)
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_create_promo")
async def a_create_promo_cb(callback: types.CallbackQuery):
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_promo_code"}
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn("a_promocodes", "🔙 Отмена")]])
    await safe_edit(callback, "🎫 Формат: <code>КОД | токены | дни</code>", kb)
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_list_promos")
async def a_list_promos_cb(callback: types.CallbackQuery):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM promocodes ORDER BY created_at DESC")
        promos = cursor.fetchall()
    text = "📋 <b>ПРОМОКОДЫ</b>\n\n"
    if not promos:
        text += "Пусто"
    else:
        for p in promos:
            text += f"🔹 <code>{p['code']}</code> +{p['bonus_tokens']}, {p['used']}/{p['max_uses']}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn("a_promocodes")]])
    await safe_edit(callback, text[:4000], kb)
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_db_status")
async def a_db_status_cb(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[[back_btn("admin_panel")]])
    await safe_edit(callback, get_queue_info(), kb)
    await helpers.safe_answer(callback)


# ==================== ЛОГИ ====================

@router.callback_query(F.data == "a_logs")
async def a_logs_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    size = os.path.getsize(LOG_PATH) if os.path.exists(LOG_PATH) else 0
    text = f"📜 <b>Логи</b>\n\n📁 {LOG_PATH}\n📦 Размер: {size / 1024:.1f} КБ"
    await safe_edit(callback, text, helpers.logs_kb())
    await helpers.safe_answer(callback)


def _read_logs(lines=100, filter_level=None):
    if not os.path.exists(LOG_PATH):
        return "❌ Файл логов не найден"
    try:
        with open(LOG_PATH, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = f.readlines()
        if filter_level:
            all_lines = [l for l in all_lines if filter_level in l]
        tail = all_lines[-lines:]
        if not tail:
            return f"📭 Нет строк с уровнем {filter_level}"
        return "".join(tail)
    except Exception as e:
        return f"❌ Ошибка чтения: {e}"


@router.callback_query(F.data == "a_logs_tail")
async def a_logs_tail_cb(callback: types.CallbackQuery):
    content = _read_logs(lines=100)
    if len(content) > 3800:
        content = "… (обрезано)\n" + content[-3800:]
    content = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    await safe_edit(callback, f"📄 <b>Последние 100 строк:</b>\n\n<pre>{content}</pre>", helpers.logs_kb())
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_logs_errors")
async def a_logs_errors_cb(callback: types.CallbackQuery):
    content = _read_logs(lines=100, filter_level="ERROR")
    if len(content) > 3800:
        content = content[-3800:]
    content = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    await safe_edit(callback, f"❌ <b>Ошибки:</b>\n\n<pre>{content}</pre>", helpers.logs_kb())
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_logs_warnings")
async def a_logs_warnings_cb(callback: types.CallbackQuery):
    content = _read_logs(lines=100, filter_level="WARNING")
    if len(content) > 3800:
        content = content[-3800:]
    content = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    await safe_edit(callback, f"⚠️ <b>Предупреждения:</b>\n\n<pre>{content}</pre>", helpers.logs_kb())
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_logs_download")
async def a_logs_download_cb(callback: types.CallbackQuery):
    if not os.path.exists(LOG_PATH):
        await helpers.safe_answer(callback, "❌ Файл не найден", show_alert=True)
        return
    try:
        with open(LOG_PATH, 'rb') as f:
            data = f.read()
        await callback.message.answer_document(
            BufferedInputFile(data, filename="bot.log"),
            caption=f"📜 bot.log ({len(data) / 1024:.1f} КБ)",
            reply_markup=helpers.logs_kb()
        )
    except Exception as e:
        await helpers.safe_answer(callback, f"❌ {e}", show_alert=True)
    await helpers.safe_answer(callback)


# ==================== АДМИН-ВВОД ====================

async def handle_admin_input(message: types.Message):
    user_id = message.from_user.id
    state = helpers.user_pages.get(user_id, {})
    state_name = state.get("state")

    if message.text == "/cancel":
        helpers.user_pages.pop(user_id, None)
        await message.answer("✅ Отменено", reply_markup=helpers.admin_kb())
        return

    if state_name == "waiting_user_search":
        await handle_user_search(message)
        return

    if state_name == "waiting_start_dialog_user":
        await handle_start_dialog(message, user_id)
        return

    if state_name == "waiting_admin_reply":
        await handle_admin_reply(message)
        return

    if state_name == "waiting_warn_add":
        await handle_warn_add(message, user_id)
        return

    if state_name == "waiting_warn_remove":
        await handle_warn_remove(message, user_id)
        return

    # === ЦЕНЫ: РЕДАКТИРОВАНИЕ ===
    if state_name == "waiting_price_edit":
        tid = state.get("tariff_id")
        t = get_tariff(tid)
        if not t:
            await message.answer("❌ Тариф не найден", reply_markup=helpers.admin_kb())
            helpers.user_pages.pop(user_id, None)
            return
        try:
            parts = [p.strip() for p in message.text.split("|")]
            name = parts[0]
            price_rub = int(parts[1])
            tokens = int(parts[2])
            stars = round(price_rub / STAR_RATE)
            if t['kind'] == "premium":
                days = int(parts[3]) if len(parts) > 3 else 30
                update_tariff(tid, name=name, price_rub=price_rub, stars=stars, tokens=tokens, days=days)
            else:
                update_tariff(tid, name=name, price_rub=price_rub, stars=stars, tokens=tokens)
            await message.answer(
                f"✅ Обновлено:\n<b>{name}</b>\n💰 {price_rub}₽\n⭐ {stars}\n🪙 {tokens}",
                reply_markup=helpers.admin_kb()
            )
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}", reply_markup=helpers.admin_kb())
        helpers.user_pages.pop(user_id, None)
        return

    # === ЦЕНЫ: ДОБАВЛЕНИЕ ===
    if state_name == "waiting_price_add":
        kind = state.get("kind", "tokens")
        try:
            parts = [p.strip() for p in message.text.split("|")]
            name = parts[0]
            price_rub = int(parts[1])
            tokens = int(parts[2])
            stars = round(price_rub / STAR_RATE)
            days = 0
            if kind == "premium":
                days = int(parts[3]) if len(parts) > 3 else 30
            add_tariff(kind, name, price_rub, stars, tokens, days)
            await message.answer(
                f"✅ Добавлено:\n<b>{name}</b>\n💰 {price_rub}₽\n⭐ {stars}\n🪙 {tokens}"
                + (f"\n📅 {days} дн." if kind == "premium" else ""),
                reply_markup=helpers.admin_kb()
            )
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}", reply_markup=helpers.admin_kb())
        helpers.user_pages.pop(user_id, None)
        return

    if state_name == "waiting_promo_code":
        try:
            parts = [p.strip() for p in message.text.split("|")]
            code = parts[0].upper()
            bonus = int(parts[1])
            days = int(parts[2]) if len(parts) > 2 else 30
            with db_connection() as conn:
                cursor = conn.cursor()
                expires = (datetime.now() + timedelta(days=days)).isoformat()
                cursor.execute(
                    "INSERT INTO promocodes (code, bonus_tokens, max_uses, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                    (code, bonus, 100, datetime.now().isoformat(), expires)
                )
            await message.answer(f"✅ Промокод <code>{code}</code> создан!", reply_markup=helpers.admin_kb())
        except Exception as e:
            await message.answer(f"❌ {e}", reply_markup=helpers.admin_kb())
        helpers.user_pages.pop(user_id, None)
        return

    if state_name == "waiting_give_tokens":
        try:
            parts = message.text.split("|")
            if parts[0].strip() in ("всем", "all"):
                amount = int(parts[1])
                with db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT user_id FROM users WHERE is_blocked = 0")
                    users = cursor.fetchall()
                for u in users:
                    add_tokens(u['user_id'], amount)
                await message.answer(f"✅ Раздано {amount} токенов {len(users)} юзерам", reply_markup=helpers.admin_kb())
            else:
                uid = int(parts[0])
                amount = int(parts[1])
                add_tokens(uid, amount)
                await message.answer(f"✅ {uid} +{amount}", reply_markup=helpers.admin_kb())
        except Exception as e:
            await message.answer(f"❌ {e}", reply_markup=helpers.admin_kb())
        helpers.user_pages.pop(user_id, None)
        return

    if state_name == "waiting_broadcast":
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE is_blocked = 0")
            users = cursor.fetchall()
        sent = 0
        for u in users:
            try:
                await message.bot.send_message(u['user_id'], f"📢 {message.text}")
                sent += 1
                await asyncio.sleep(0.05)
            except Exception:
                pass
        await message.answer(f"✅ Отправлено: {sent}", reply_markup=helpers.admin_kb())
        helpers.user_pages.pop(user_id, None)
        return
