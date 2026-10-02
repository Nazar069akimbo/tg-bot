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


def get_users_from_db():
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, tokens, is_blocked FROM users ORDER BY tokens DESC LIMIT 50")
        return cursor.fetchall()


def get_promocodes_from_db():
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM promocodes ORDER BY created_at DESC")
        return cursor.fetchall()


@router.callback_query(F.data == "a_stats")
async def a_stats_cb(callback: types.CallbackQuery):
    total, total_tokens, premium_users = get_stats()
    text = f"📊 СТАТИСТИКА\n\n👥 Всего: {total}\n💎 Премиум: {premium_users}\n💰 Токенов: {total_tokens}"
    await safe_edit(callback, text, helpers.admin_kb())
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_users")
async def a_users_cb(callback: types.CallbackQuery):
    users = get_users_from_db()
    text = "👥 Топ пользователей\n\n"
    for u in users:
        status = "⛔" if u['is_blocked'] == 1 else "✅"
        name = u['username'] or str(u['user_id'])
        text += f"{status} {name}: {u['tokens']} токенов\n"
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
    users = get_users_from_db()
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
    result = GitHubBackup().restore_latest_backup()
    await safe_edit(callback, "✅ Восстановлено!" if result else "❌ Ошибка", helpers.admin_kb())
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
    promos = get_promocodes_from_db()
    text = "📋 ПРОМОКОДЫ\n\n"
    for p in promos:
        text += f"🔹 {p['code']} +{p['bonus_tokens']}, {p['used']}/{p['max_uses']}\n"
    await safe_edit(callback, text[:4000] or "Нет", helpers.admin_kb())
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "a_db_status")
async def a_db_status_cb(callback: types.CallbackQuery):
    await safe_edit(callback, get_queue_info(), helpers.admin_kb())
    await helpers.safe_answer(callback)


# ===== ТАРИФЫ =====
@router.callback_query(F.data == "a_tariffs")
async def a_tariffs_cb(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Пакеты токенов", callback_data="a_tariff_kind_tokens")],
        [InlineKeyboardButton(text="💎 Подписки", callback_data="a_tariff_kind_premium")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    await safe_edit(callback, "🎫 УПРАВЛЕНИЕ ТАРИФАМИ", kb)
    await helpers.safe_answer(callback)


@router.callback_query(F.data.startswith("a_tariff_kind_"))
async def a_tariff_kind_cb(callback: types.CallbackQuery):
    kind = callback.data.replace("a_tariff_kind_", "")
    tariffs = get_tariffs(kind)
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for t in tariffs:
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"✏️ {t['name']} — {t['price_rub']}₽", callback_data=f"a_tariff_edit_{t['id']}")])
        kb.inline_keyboard.append([InlineKeyboardButton(text="🗑 Удалить", callback_data=f"a_tariff_del_{t['id']}")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="➕ Добавить", callback_data=f"a_tariff_add_{kind}")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="a_tariffs")])
    title = "📦 ПАКЕТЫ" if kind == "tokens" else "💎 ПОДПИСКИ"
    await safe_edit(callback, f"{title}\n\nНажми ✏️ чтобы изменить", kb)
    await helpers.safe_answer(callback)


@router.callback_query(F.data.startswith("a_tariff_edit_"))
async def a_tariff_edit_cb(callback: types.CallbackQuery):
    tid = int(callback.data.replace("a_tariff_edit_", ""))
    t = get_tariff(tid)
    if not t:
        return
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_tariff_edit", "tariff_id": tid}
    await safe_edit(callback, f"✏️ {t['name']}\n\nВведи: название | цена_руб | токены | дни\nПример: Базовый | 200 | 1800 | 0", None)
    await helpers.safe_answer(callback)


@router.callback_query(F.data.startswith("a_tariff_del_"))
async def a_tariff_del_cb(callback: types.CallbackQuery):
    tid = int(callback.data.replace("a_tariff_del_", ""))
    delete_tariff(tid)
    await helpers.safe_answer(callback, "✅ Удалено", show_alert=True)
    await a_tariffs_cb(callback)


@router.callback_query(F.data.startswith("a_tariff_add_"))
async def a_tariff_add_cb(callback: types.CallbackQuery):
    kind = callback.data.replace("a_tariff_add_", "")
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_tariff_add", "kind": kind}
    await safe_edit(callback, "➕ Введи: название | цена_руб | токены | дни", None)
    await helpers.safe_answer(callback)


async def handle_admin_input(message: types.Message):
    user_id = message.from_user.id
    state = helpers.user_pages.get(user_id, {})

    if message.text == "/cancel":
        helpers.user_pages.pop(user_id, None)
        await message.answer("✅ Отменено", reply_markup=helpers.admin_kb())
        return

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

    if state.get("state") == "waiting_tariff_edit":
        try:
            parts = [p.strip() for p in message.text.split("|")]
            name = parts[0]
            price_rub = int(parts[1])
            tokens = int(parts[2])
            days = int(parts[3]) if len(parts) > 3 else 0
            stars = round(price_rub / STAR_RATE)
            update_tariff(state["tariff_id"], name=name, price_rub=price_rub, tokens=tokens, stars=stars, days=days)
            await message.answer(f"✅ Обновлено: {name} — {price_rub}₽ ({stars} ⭐)", reply_markup=helpers.admin_kb())
        except Exception as e:
            await message.answer(f"❌ {e}", reply_markup=helpers.admin_kb())
        helpers.user_pages.pop(user_id, None)
        return

    if state.get("state") == "waiting_tariff_add":
        try:
            parts = [p.strip() for p in message.text.split("|")]
            name = parts[0]
            price_rub = int(parts[1])
            tokens = int(parts[2])
            days = int(parts[3]) if len(parts) > 3 else 0
            stars = round(price_rub / STAR_RATE)
            add_tariff(state["kind"], name, price_rub, stars, tokens, days)
            await message.answer(f"✅ Добавлено: {name}", reply_markup=helpers.admin_kb())
        except Exception as e:
            await message.answer(f"❌ {e}", reply_markup=helpers.admin_kb())
        helpers.user_pages.pop(user_id, None)
        return
