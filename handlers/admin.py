from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from . import helpers
from backup import GitHubBackup
import logging, os

router = Router()
logger = logging.getLogger(__name__)

ADMIN_CODE = "30121979"

@router.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if is_admin(message.from_user.id):
        await message.answer("🛡️ **АДМИН-ПАНЕЛЬ**", reply_markup=helpers.admin_kb())
    else:
        await message.answer("🔐 Введите код: /admin_code 30121979")

@router.message(Command("admin_code"))
async def admin_code_cmd(message: types.Message):
    args = message.text.split() if message.text else []
    if len(args) > 1 and args[1] == ADMIN_CODE:
        add_admin(message.from_user.id)
        await message.answer("✅ Вы админ!", reply_markup=helpers.admin_kb())

@router.callback_query(F.data == "admin_panel")
async def admin_panel_cb(callback: types.CallbackQuery):
    if is_admin(callback.from_user.id):
        await safe_edit(callback, "🛡️ **АДМИН-ПАНЕЛЬ**", helpers.admin_kb())
    else:
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)

# ===== БЕЗОПАСНОЕ РЕДАКТИРОВАНИЕ =====
async def safe_edit(callback, text, reply_markup=None):
    """Безопасное редактирование сообщения"""
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except Exception as e:
        if "there is no text in the message to edit" in str(e) or "message is not modified" in str(e):
            # Если нечего редактировать — отправляем новое сообщение
            await callback.message.answer(text, reply_markup=reply_markup)
        else:
            raise

@router.callback_query(F.data == "a_stats")
async def a_stats_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    total, total_tokens, total_requests, total_images, premium_users = get_stats()
    text = (
        f"📊 **СТАТИСТИКА**\n\n"
        f"👥 Всего: {total}\n"
        f"💎 Премиум: {premium_users}\n"
        f"💰 Токенов: {total_tokens}\n"
        f"📝 Запросов: {total_requests}\n"
        f"🖼️ Картинок: {total_images}"
    )
    await safe_edit(callback, text, helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_model_stats")
async def a_model_stats_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    total = sum(helpers.model_stats.values())
    if total > 0:
        text = "📈 **МОДЕЛИ**\n\nВсего: " + str(total) + "\n\n"
        for key, count in helpers.model_stats.items():
            if count > 0:
                model = helpers.IMAGE_MODELS[key]
                text += f"{model['name']}: {count} ({round(count/total*100,1)}%)\n"
    else:
        text = "📈 **МОДЕЛИ**\n\n❌ Нет статистики."
    await safe_edit(callback, text, helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_users")
async def a_users_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    conn = sqlite3.connect('data/repsolver.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, tokens, is_blocked FROM users WHERE user_id != 8676871187 ORDER BY tokens DESC LIMIT 20")
    users = cursor.fetchall()
    conn.close()
    if not users:
        text = "👥 Нет пользователей"
    else:
        text = "👥 **Топ**\n\n"
        for u in users:
            status = "⛔" if u['is_blocked'] == 1 else "✅"
            name = u['username'] if u['username'] and u['username'] != str(u['user_id']) else "Без имени"
            text += f"{status} {name}: {u['tokens']} токенов\n"
    await safe_edit(callback, text[:4000], helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_give_tokens")
async def a_give_tokens_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_give_tokens"}
    await safe_edit(callback, "⭐ **Раздать токены**\n\nФормат: `ID | кол-во` или `всем | кол-во`", helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_broadcast")
async def a_broadcast_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_broadcast"}
    await safe_edit(callback, "📢 **Рассылка**\n\nВведите текст.", helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_block")
async def a_block_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    conn = sqlite3.connect('data/repsolver.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, is_blocked FROM users WHERE user_id != 8676871187 LIMIT 20")
    users = cursor.fetchall()
    conn.close()
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for u in users:
        name = u['username'] if u['username'] and u['username'] != str(u['user_id']) else str(u['user_id'])
        status = "✅" if u['is_blocked'] == 0 else "⛔"
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{status} {name}", callback_data=f"block_user_{u['user_id']}")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])
    await safe_edit(callback, "🚫 **Блокировка**\n\nНажмите на пользователя:", kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("block_user_"))
async def block_user_action(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    user_id = int(callback.data.replace("block_user_", ""))
    user = get_user(user_id)
    if not user:
        await helpers.safe_answer(callback, "❌ Не найден", show_alert=True)
        return
    if user['is_blocked'] == 1:
        unblock_user(user_id)
        await helpers.safe_answer(callback, "✅ Разблокирован", show_alert=True)
    else:
        block_user(user_id)
        await helpers.safe_answer(callback, "⛔ Заблокирован", show_alert=True)
    do_backup()
    await a_block_cb(callback)

@router.callback_query(F.data == "a_messages")
async def a_messages_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    conn = sqlite3.connect('data/repsolver.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, username, text, date FROM messages_to_admin ORDER BY date DESC LIMIT 20")
    msgs = cursor.fetchall()
    conn.close()
    if not msgs:
        await safe_edit(callback, "📭 Нет обращений.", helpers.admin_kb())
        await helpers.safe_answer(callback)
        return
    text = "📩 **Обращения**\n\n"
    for m in msgs:
        name = m['username'] if m['username'] and m['username'] != str(m['user_id']) else str(m['user_id'])
        text += f"👤 {name}: {m['text'][:50]}\n🕐 {m['date'][:16]}\n\n"
    await safe_edit(callback, text[:4000], helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_backup")
async def a_backup_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    await safe_edit(callback, "⏳ Бэкап...", None)
    result = GitHubBackup().backup_db()
    await safe_edit(callback, "✅ Бэкап создан!" if result else "❌ Ошибка", helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_export_db")
async def export_db_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    if not os.path.exists('data/repsolver.db'):
        await safe_edit(callback, "❌ БД не найдена", helpers.admin_kb())
        await helpers.safe_answer(callback)
        return
    try:
        await callback.message.delete()
        await callback.message.answer_document(
            BufferedInputFile(open('data/repsolver.db', 'rb').read(), filename="repsolver.db"),
            caption="📁 База данных", reply_markup=helpers.admin_kb()
        )
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}", reply_markup=helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_restore_github")
async def restore_github_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    result = GitHubBackup().restore_latest_backup()
    await safe_edit(callback, "✅ БД восстановлена!" if result else "❌ Ошибка", helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_edit_prices")
async def a_edit_prices_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for key, model in helpers.IMAGE_MODELS.items():
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{model['name']} — {model['price']} токенов", callback_data=f"edit_price_{key}")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])
    await safe_edit(callback, "💰 **Цены**\n\nВыбери модель:", kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("edit_price_"))
async def edit_price_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    model_key = callback.data.replace("edit_price_", "")
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_price", "model": model_key}
    await safe_edit(callback, f"💰 Введи новую цену для {helpers.IMAGE_MODELS[model_key]['name']}:", helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_promocodes")
async def a_promocodes_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать", callback_data="a_create_promo")],
        [InlineKeyboardButton(text="📋 Список", callback_data="a_list_promos")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    await safe_edit(callback, "🎫 **Промокоды**", kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_create_promo")
async def a_create_promo_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_promo_code"}
    await safe_edit(callback, "🎫 **Создание**\n\nФормат: `код | токены | дни`\n\nПример: `WELCOME | 100 | 30`", helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_list_promos")
async def a_list_promos_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    conn = sqlite3.connect('data/repsolver.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM promocodes ORDER BY created_at DESC")
    promos = cursor.fetchall()
    conn.close()
    if not promos:
        await safe_edit(callback, "📋 Нет промокодов", helpers.admin_kb())
        await helpers.safe_answer(callback)
        return
    text = "📋 **Промокоды**\n\n"
    for p in promos:
        text += f"🔹 `{p['code']}` +{p['bonus_tokens']} токенов, {p['used']}/{p['max_uses']}, до {p['expires_at'][:10]}\n"
    await safe_edit(callback, text[:4000], helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_stars_balance")
async def a_stars_balance_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    try:
        balance = await callback.bot.get_my_star_balance()
        byn = balance * 0.013
        rub = balance * 0.45
        text = (
            f"⭐ **Баланс Stars**\n\n"
            f"На счету: {balance} Stars\n"
            f"💵 ≈ {byn:.2f} BYN ≈ {rub:.2f} ₽\n"
            f"💡 Мин. вывод: 1000 Stars"
        )
        await safe_edit(callback, text, helpers.admin_kb())
    except Exception as e:
        await safe_edit(callback, f"❌ Ошибка: {e}", helpers.admin_kb())
    await helpers.safe_answer(callback)
