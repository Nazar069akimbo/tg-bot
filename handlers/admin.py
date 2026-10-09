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


@router.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if is_admin(message.from_user.id):
        await message.answer("🛡️ АДМИН-ПАНЕЛЬ", reply_markup=helpers.admin_kb())
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
        await safe_edit(callback, "🛡️ АДМИН-ПАНЕЛЬ", helpers.admin_kb())


async def safe_edit(callback, text, reply_markup=None):
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        await callback.message.answer(text, reply_markup=reply_markup)


# ===== СТАТИСТИКА =====
@router.callback_query(F.data == "a_stats")
async def a_stats_cb(callback: types.CallbackQuery):
    total, total_tokens, premium_users = get_stats()
    today = get_users_count_today()
    week = get_users_count_week()

    text = (
        f"📊 **СТАТИСТИКА**\n\n"
        f"👥 Всего: {total}\n"
        f"🆕 Сегодня: {today}\n"
        f"📅 За неделю: {week}\n"
        f"💎 Премиум: {premium_users}\n"
        f"💰 Токенов: {total_tokens}"
    )
    await safe_edit(callback, text, helpers.admin_kb())
    await helpers.safe_answer(callback)


# ===== ПОИСК ПОЛЬЗОВАТЕЛЕЙ =====
@router.callback_query(F.data == "a_search_users")
async def a_search_users_cb(callback: types.CallbackQuery):
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_user_search"}
    await safe_edit(callback,
        "🔍 **Поиск пользователей**\n\n"
        "Введи имя, username или ID.\n\n"
        "⏹ /cancel — отмена",
        helpers.admin_kb()
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
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    await safe_edit(callback, "🎯 **Фильтры**\n\nВыбери:", kb)
    await helpers.safe_answer(callback)


@router.callback_query(F.data.startswith("a_filter|"))
async def a_filter_cb(callback: types.CallbackQuery):
    filter_type = callback.data.split("|")[1]
    users = search_users(filter_type=filter_type, limit=30)

    text = f"🎯 **Фильтр: {filter_type}**\n\n"
    for u in users:
        name = u['username'] or str(u['user_id'])
        status = "⛔" if u['is_blocked'] else "✅"
        plan = "💎" if u['plan'] in ('premium', 'premium_plus') else "👤"
        text += f"{status}{plan} {name}: {u['tokens']} ток.\n"

    if not users:
        text += "Пусто."

    await safe_edit(callback, text[:4000], helpers.admin_kb())
    await helpers.safe_answer(callback)


async def handle_user_search(message: types.Message):
    user_id = message.from_user.id
    query = message.text.strip()

    if query == "/cancel":
        helpers.user_pages.pop(user_id, None)
        await message.answer("✅ Отменено", reply_markup=helpers.admin_kb())
        return

    users = search_users(query=query, limit=30)

    if not users:
        await message.answer(f"❌ Ничего не найдено по `{query}`", reply_markup=helpers.admin_kb())
    else:
        text = f"🔍 **Результаты: {query}**\n\n"
        for u in users:
            name = u['username'] or str(u['user_id'])
            status = "⛔" if u['is_blocked'] else "✅"
            plan = "💎" if u['plan'] in ('premium', 'premium_plus') else "👤"
            text += f"{status}{plan} {name} (ID: {u['user_id']}): {u['tokens']} ток.\n"
        await message.answer(text[:4000], reply_markup=helpers.admin_kb())

    helpers.user_pages.pop(user_id, None)


# ===== БАЛАНС ЗВЁЗД =====
@router.callback_query(F.data == "a_stars_balance")
async def a_stars_balance_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    try:
        balance = await callback.bot.get_my_star_balance()
        rub = balance * 0.45
        byn = balance * 0.013
        text = (
            f"⭐ **Баланс Stars**\n\n"
            f"На счету: {balance} Stars\n"
            f"💵 ≈ {rub:.2f} ₽\n"
            f"💶 ≈ {byn:.2f} BYN\n"
            f"💡 Мин. вывод: 1000 Stars"
        )
        await safe_edit(callback, text, helpers.admin_kb())
    except Exception as e:
        await safe_edit(callback, f"❌ Ошибка: {e}", helpers.admin_kb())
    await helpers.safe_answer(callback)


# ===== ТИКЕТЫ ПОДДЕРЖКИ =====
@router.callback_query(F.data == "a_support_tickets")
async def a_support_tickets_cb(callback: types.CallbackQuery):
    tickets = get_support_tickets(status='open', limit=20)

    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for t in tickets:
        name = t['username'] or str(t['user_id'])
        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"💬 #{t['id']} {name}",
                callback_data=f"a_ticket_{t['id']}"
            )
        ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])

    await safe_edit(callback, f"📩 **Открытые тикеты: {len(tickets)}**\n\nВыбери:", kb)
    await helpers.safe_answer(callback)


@router.callback_query(F.data.startswith("a_ticket_"))
async def a_ticket_cb(callback: types.CallbackQuery):
    ticket_id = int(callback.data.replace("a_ticket_", ""))
    msgs = get_ticket_messages(ticket_id)

    text = f"💬 **Тикет #{ticket_id}**\n\n"
    for m in msgs[-30:]:
        who = "👤 User" if m['sender'] == 'user' else "🛡 Admin"
        text += f"{who}: {m['text']}\n"

    helpers.user_pages[callback.from_user.id] = {"state": "waiting_admin_reply", "ticket_id": ticket_id}

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Ответить", callback_data=f"a_reply_{ticket_id}")],
        [InlineKeyboardButton(text="✅ Закрыть", callback_data=f"a_close_{ticket_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="a_support_tickets")]
    ])

    await safe_edit(callback, text[:4000], kb)
    await helpers.safe_answer(callback)


@router.callback_query(F.data.startswith("a_reply_"))
async def a_reply_cb(callback: types.CallbackQuery):
    ticket_id = int(callback.data.replace("a_reply_", ""))
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_admin_reply", "ticket_id": ticket_id}
    await safe_edit(callback, f"✍️ Напиши ответ для тикета #{ticket_id}:", None)
    await helpers.safe_answer(callback)


@router.callback_query(F.data.startswith("a_close_"))
async def a_close_cb(callback: types.CallbackQuery):
    ticket_id = int(callback.data.replace("a_close_", ""))
    close_ticket(ticket_id)
    await helpers.safe_answer(callback, "✅ Тикет закрыт", show_alert=True)
    await a_support_tickets_cb(callback)


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

    # Сохраняем ответ
    add_support_message(ticket_id, 'admin', text)

    # Отправляем пользователю
    try:
        ticket = get_support_tickets()
        ticket_data = next((t for t in ticket if t['id'] == ticket_id), None)
        if ticket_data:
            user_tg_id = ticket_data['user_id']
            await message.bot.send_message(user_tg_id, f"💬 **Ответ поддержки:**\n\n{text}")
    except Exception as e:
        logger.warning(f"⚠️ Не отправил юзеру: {e}")

    await message.answer(f"✅ Ответ отправлен в тикет #{ticket_id}", reply_markup=helpers.admin_kb())
    helpers.user_pages.pop(user_id, None)


# ===== ОСТАЛЬНЫЕ КНОПКИ =====
@router.callback_query(F.data == "a_users")
async def a_users_cb(callback: types.CallbackQuery):
    users = search_users(limit=50)
    text = "👥 **Топ по токенам**\n\n"
    for u in users:
        status = "⛔" if u['is_blocked'] else "✅"
        name = u['username'] or str(u['user_id'])
        text += f"{status} {name}: {u['tokens']}\n"
    await safe_edit(callback, text[:4000], helpers.admin_kb())
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_give_tokens")
async def a_give_tokens_cb(callback: types.CallbackQuery):
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_give_tokens"}
    await safe_edit(callback, "⭐ РАЗДАТЬ ТОКЕНЫ\n\nФормат: ID | кол-во", helpers.admin_kb())
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_broadcast")
async def a_broadcast_cb(callback: types.CallbackQuery):
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_broadcast"}
    await safe_edit(callback, "📢 РАССЫЛКА\n\nВведите текст.", helpers.admin_kb())
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_block")
async def a_block_cb(callback: types.CallbackQuery):
    users = search_users(limit=30)
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for u in users:
        name = u['username'] or str(u['user_id'])
        status = "✅" if u['is_blocked'] == 0 else "⛔"
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{status} {name}", callback_data=f"block_user_{u['user_id']}")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])
    await safe_edit(callback, "🚫 БЛОКИРОВКА", kb)
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


@router.callback_query(F.data == "a_messages")
async def a_messages_cb(callback: types.CallbackQuery):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, text, date FROM messages_to_admin ORDER BY date DESC LIMIT 20")
        msgs = cursor.fetchall()
    text = "📩 ОБРАЩЕНИЯ\n\n"
    for m in msgs:
        text += f"👤 {m['username'] or m['user_id']}: {m['text'][:50]}\n"
    await safe_edit(callback, text[:4000] or "Нет обращений", helpers.admin_kb())
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_backup")
async def a_backup_cb(callback: types.CallbackQuery):
    await safe_edit(callback, "⏳ Бэкап...", None)
    result = GitHubBackup().backup_all(reason='вручную')
    await safe_edit(callback, "✅ Готово!" if result else "❌ Ошибка", helpers.admin_kb())
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
    await safe_edit(callback, "⏳ Восстанавливаю пользователей...", None)
    result = GitHubBackup().restore_users()
    await safe_edit(callback, "✅ Пользователи восстановлены!" if result else "❌ Ошибка", helpers.admin_kb())
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_promocodes")
async def a_promocodes_cb(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать", callback_data="a_create_promo")],
        [InlineKeyboardButton(text="📋 Список", callback_data="a_list_promos")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    await safe_edit(callback, "🎫 ПРОМОКОДЫ", kb)
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_create_promo")
async def a_create_promo_cb(callback: types.CallbackQuery):
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_promo_code"}
    await safe_edit(callback, "🎫 Формат: код | токены | дни", helpers.admin_kb())
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_list_promos")
async def a_list_promos_cb(callback: types.CallbackQuery):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM promocodes ORDER BY created_at DESC")
        promos = cursor.fetchall()
    text = "📋 ПРОМОКОДЫ\n\n"
    for p in promos:
        text += f"🔹 {p['code']} +{p['bonus_tokens']}, {p['used']}/{p['max_uses']}\n"
    await safe_edit(callback, text[:4000] or "Нет", helpers.admin_kb())
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_db_status")
async def a_db_status_cb(callback: types.CallbackQuery):
    await safe_edit(callback, get_queue_info(), helpers.admin_kb())
    await helpers.safe_answer(callback)


# ===== АДМИН-ВВОД =====
async def handle_admin_input(message: types.Message):
    user_id = message.from_user.id
    state = helpers.user_pages.get(user_id, {})

    if message.text == "/cancel":
        helpers.user_pages.pop(user_id, None)
        await message.answer("✅ Отменено", reply_markup=helpers.admin_kb())
        return

    # Поиск юзеров
    if state.get("state") == "waiting_user_search":
        await handle_user_search(message)
        return

    # Ответ в тикет
    if state.get("state") == "waiting_admin_reply":
        await handle_admin_reply(message)
        return

    # Промокод
    if state.get("state") == "waiting_promo_code":
        try:
            parts = [p.strip() for p in message.text.split("|")]
            code = parts[0].upper()
            bonus = int(parts[1])
            days = int(parts[2]) if len(parts) > 2 else 30
            with db_connection() as conn:
                cursor = conn.cursor()
                expires = (datetime.now() + timedelta(days=days)).isoformat()
                cursor.execute("INSERT INTO promocodes (code, bonus_tokens, max_uses, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                              (code, bonus, 100, datetime.now().isoformat(), expires))
            await message.answer(f"✅ Промокод {code} создан!", reply_markup=helpers.admin_kb())
        except Exception as e:
            await message.answer(f"❌ {e}", reply_markup=helpers.admin_kb())
        helpers.user_pages.pop(user_id, None)
        return

    # Раздача токенов
    if state.get("state") == "waiting_give_tokens":
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

    # Рассылка
    if state.get("state") == "waiting_broadcast":
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
