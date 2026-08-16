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
        await callback.message.edit_text("🛡️ **АДМИН-ПАНЕЛЬ**", reply_markup=helpers.admin_kb())
        await helpers.safe_answer(callback)
    else:
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)

@router.callback_query(F.data == "a_stats")
async def a_stats_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    total, total_tokens, total_requests, total_images, premium_users = get_stats()
    await callback.message.edit_text(
        f"📊 **СТАТИСТИКА**\n\n👥 Всего: {total}\n💎 Премиум: {premium_users}\n💰 Токенов: {total_tokens}\n📝 Запросов: {total_requests}\n🖼️ Картинок: {total_images}",
        reply_markup=helpers.admin_kb()
    )
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_model_stats")
async def a_model_stats_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    total = sum(helpers.model_stats.values())
    text = "📈 **МОДЕЛИ**\n\n" + (f"Всего: {total}\n\n" if total > 0 else "❌ Нет статистики.")
    for key, count in helpers.model_stats.items():
        if count > 0:
            model = helpers.IMAGE_MODELS[key]
            text += f"{model['name']}: {count} ({round(count/total*100,1)}%)\n"
    await callback.message.edit_text(text, reply_markup=helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_users")
async def a_users_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, tokens, is_blocked FROM users WHERE user_id != 8676871187 ORDER BY tokens DESC LIMIT 20")
    users = cursor.fetchall()
    conn.close()
    text = "👥 **Топ**\n\n"
    for u in users:
        status = "⛔" if u['is_blocked'] == 1 else "✅"
        name = u['username'] if u['username'] and u['username'] != str(u['user_id']) else "Без имени"
        text += f"{status} {name}: {u['tokens']} токенов\n"
    await callback.message.edit_text(text[:4000], reply_markup=helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_give_tokens")
async def a_give_tokens_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_give_tokens"}
    await callback.message.edit_text("⭐ **Раздать токены**\n\nФормат: `ID | кол-во` или `всем | кол-во`", reply_markup=helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_broadcast")
async def a_broadcast_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_broadcast"}
    await callback.message.edit_text("📢 **Рассылка**\n\nВведите текст.", reply_markup=helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_block")
async def a_block_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    conn = get_db()
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
    await callback.message.edit_text("🚫 **Блокировка**", reply_markup=kb)
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
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, username, text, date FROM messages_to_admin ORDER BY date DESC LIMIT 20")
    msgs = cursor.fetchall()
    conn.close()
    if not msgs:
        await callback.message.edit_text("📭 Нет обращений.", reply_markup=helpers.admin_kb())
        await helpers.safe_answer(callback)
        return
    text = "📩 **Обращения**\n\n"
    for m in msgs:
        name = m['username'] if m['username'] and m['username'] != str(m['user_id']) else str(m['user_id'])
        text += f"👤 {name}: {m['text'][:50]}\n🕐 {m['date'][:16]}\n\n"
    await callback.message.edit_text(text[:4000], reply_markup=helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_backup")
async def a_backup_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("⏳ Бэкап...")
    result = GitHubBackup().backup_db()
    await callback.message.edit_text("✅ Бэкап создан!" if result else "❌ Ошибка", reply_markup=helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_export_db")
async def export_db_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    if not os.path.exists('data/repsolver.db'):
        await callback.message.edit_text("❌ БД не найдена", reply_markup=helpers.admin_kb())
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
    await callback.message.edit_text("✅ БД восстановлена!" if result else "❌ Ошибка", reply_markup=helpers.admin_kb())
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
    await callback.message.edit_text("💰 **Цены**", reply_markup=kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("edit_price_"))
async def edit_price_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    model_key = callback.data.replace("edit_price_", "")
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_price", "model": model_key}
    await callback.message.edit_text(f"💰 Введи новую цену для {helpers.IMAGE_MODELS[model_key]['name']}:", reply_markup=helpers.admin_kb())
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
    await callback.message.edit_text("🎫 **Промокоды**", reply_markup=kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_create_promo")
async def a_create_promo_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_promo_code"}
    await callback.message.edit_text("🎫 **Создание**\n\nФормат: `код | токены | дни`", reply_markup=helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_list_promos")
async def a_list_promos_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM promocodes ORDER BY created_at DESC")
    promos = cursor.fetchall()
    conn.close()
    if not promos:
        await callback.message.edit_text("📋 Нет промокодов", reply_markup=helpers.admin_kb())
        await helpers.safe_answer(callback)
        return
    text = "📋 **Промокоды**\n\n"
    for p in promos:
        text += f"🔹 `{p['code']}` +{p['bonus_tokens']} токенов, {p['used']}/{p['max_uses']}, до {p['expires_at'][:10]}\n"
    await callback.message.edit_text(text[:4000], reply_markup=helpers.admin_kb())
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
        await callback.message.edit_text(
            f"⭐ **Баланс Stars**\n\nНа счету: {balance} Stars\n💵 ≈ {byn:.2f} BYN ≈ {rub:.2f} ₽\n💡 Мин. вывод: 1000 Stars",
            reply_markup=helpers.admin_kb()
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=helpers.admin_kb())
    await helpers.safe_answer(callback)
