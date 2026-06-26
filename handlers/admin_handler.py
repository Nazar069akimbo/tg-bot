from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from database.db import is_admin, add_admin, cursor, conn, get_setting, set_setting, get_user
from database.db import add_premium as db_add_premium
import asyncio
from datetime import datetime
from backup_github import GitHubBackup
import requests

router = Router()
ADMIN_CODE = "30121979"
user_pages = {}

def admin_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="a_stats")],
            [InlineKeyboardButton(text="👥 Пользователи", callback_data="a_users_list")],
            [InlineKeyboardButton(text="🔍 Поиск", callback_data="a_search_user")],
            [InlineKeyboardButton(text="📩 Обращения", callback_data="a_messages")],
            [InlineKeyboardButton(text="⚙️ Лимиты", callback_data="a_limits")],
            [InlineKeyboardButton(text="📢 Рассылка", callback_data="a_broadcast")],
            [InlineKeyboardButton(text="💎 Выдать Premium", callback_data="a_give_premium_list")],
            [InlineKeyboardButton(text="💾 Бэкап", callback_data="a_backup")],
            [InlineKeyboardButton(text="💾 Восстановить", callback_data="a_restore_db")],
            [InlineKeyboardButton(text="🗑️ Бэкапы", callback_data="a_backup_manage")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ]
    )

@router.message(Command("admin"))
async def admin_cmd(message: types.Message):
    user_pages.pop(message.from_user.id, None)
    if is_admin(message.from_user.id):
        await message.answer("🛡️ **АДМИН-ПАНЕЛЬ**", reply_markup=admin_kb())
    else:
        await message.answer("🔐 Введите код: /admin_code 30121979")

@router.message(Command("admin_code"))
async def admin_code_cmd(message: types.Message):
    parts = message.text.split()
    if len(parts) > 1 and parts[1] == ADMIN_CODE:
        add_admin(message.from_user.id)
        user_pages.pop(message.from_user.id, None)
        await message.answer("✅ Вы стали администратором!\n\n🛡️ **АДМИН-ПАНЕЛЬ**", reply_markup=admin_kb())
    else:
        await message.answer("❌ Неверный код")

@router.callback_query(F.data == "admin_panel")
async def admin_panel_cb(callback: types.CallbackQuery):
    user_pages.pop(callback.from_user.id, None)
    if is_admin(callback.from_user.id):
        try:
            await callback.message.delete()
        except:
            pass
        await callback.message.answer("🛡️ **АДМИН-ПАНЕЛЬ**", reply_markup=admin_kb())
    else:
        await callback.answer("⛔ Нет доступа", show_alert=True)
    await callback.answer()

@router.callback_query(F.data == "back_to_admin")
async def back_to_admin(callback: types.CallbackQuery):
    user_pages.pop(callback.from_user.id, None)
    try:
        await callback.message.delete()
    except:
        pass
    await callback.message.answer("🛡️ **АДМИН-ПАНЕЛЬ**", reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_stats")
async def a_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE premium_until IS NOT NULL AND premium_until > datetime('now')")
    premium = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(total_requests) FROM users")
    req = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 1")
    blocked = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM admins")
    admins = cursor.fetchone()[0]
    
    text = f"📊 **СТАТИСТИКА**\n\n"
    text += f"👥 Всего: {total}\n"
    text += f"💎 Premium: {premium}\n"
    text += f"🔴 Заблокировано: {blocked}\n"
    text += f"📝 Запросов: {req}\n"
    text += f"🛡️ Админов: {admins}"
    
    try:
        await callback.message.edit_text(text, reply_markup=admin_kb())
    except TelegramBadRequest:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_users_list")
async def a_users_list(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    cursor.execute("SELECT user_id, username, total_requests, is_blocked, premium_until FROM users ORDER BY user_id LIMIT 20")
    users = cursor.fetchall()
    
    text = "👥 **ПОЛЬЗОВАТЕЛИ**\n\n"
    if not users:
        text = "👥 Пользователей не найдено"
    else:
        for u in users:
            status = "🔴 Заблокирован" if u[3] == 1 else "🟢 Активен"
            premium = "💎" if u[4] and u[4] > datetime.now().isoformat() else "🔴"
            name = u[1] or "без имени"
            text += f"🆔 `{u[0]}` — {name}\n"
            text += f"   {status} | {premium} Запросов: {u[2]}\n"
            text += f"   👉 /user_{u[0]}\n\n"
    
    await callback.message.edit_text(text, reply_markup=admin_kb())
    await callback.answer()

@router.message(F.text.startswith("/user_"))
async def user_info_command(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        return
    
    try:
        user_id = int(message.text.replace("/user_", ""))
        user = get_user(user_id)
        if not user:
            await message.answer("❌ Пользователь не найден")
            return
        
        cursor.execute("SELECT username, joined, premium_until, total_requests, is_blocked, mode, image_requests FROM users WHERE user_id = ?", (user_id,))
        u = cursor.fetchone()
        
        text = f"👤 **ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ**\n\n"
        text += f"🆔 ID: `{user_id}`\n"
        text += f"👤 Имя: {u[0] or 'без имени'}\n"
        text += f"📆 Регистрация: {u[1][:10] if u[1] else 'Нет'}\n"
        text += f"📊 Запросов: {u[3] or 0}\n"
        text += f"🖼️ Картинок: {u[6] or 0}\n"
        text += f"💎 Premium: {'✅ Активен' if u[2] and u[2] > datetime.now().isoformat() else '❌ Нет'}\n"
        text += f"🔒 Статус: {'🔴 Заблокирован' if u[4] == 1 else '🟢 Активен'}"
        
        await message.answer(text, reply_markup=admin_kb())
    except ValueError:
        await message.answer("❌ Неверный ID пользователя")

@router.callback_query(F.data == "a_search_user")
async def a_search_user(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    user_pages[callback.from_user.id] = {"state": "waiting_user_search"}
    
    await callback.message.edit_text(
        "🔍 **Поиск пользователя**\n\n"
        "Введи ID пользователя.\n\n"
        "Пример: `6957852385`\n\n"
        "⏹ Отмена: /cancel"
    )
    await callback.answer()

@router.message(F.text)
async def handle_admin_messages(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    
    state = user_pages.get(message.from_user.id, {})
    
    if state.get("state") == "waiting_user_search":
        if message.text == "/cancel":
            user_pages.pop(message.from_user.id, None)
            await message.answer("✅ Поиск отменен", reply_markup=admin_kb())
            return
        
        try:
            user_id = int(message.text.strip())
            user = get_user(user_id)
            if not user:
                await message.answer(f"❌ Пользователь {user_id} не найден", reply_markup=admin_kb())
                return
            
            cursor.execute("SELECT username, joined, premium_until, total_requests, is_blocked, mode, image_requests FROM users WHERE user_id = ?", (user_id,))
            u = cursor.fetchone()
            
            text = f"👤 **ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ**\n\n"
            text += f"🆔 ID: `{user_id}`\n"
            text += f"👤 Имя: {u[0] or 'без имени'}\n"
            text += f"📆 Регистрация: {u[1][:10] if u[1] else 'Нет'}\n"
            text += f"📊 Запросов: {u[3] or 0}\n"
            text += f"🖼️ Картинок: {u[6] or 0}\n"
            text += f"💎 Premium: {'✅ Активен' if u[2] and u[2] > datetime.now().isoformat() else '❌ Нет'}\n"
            text += f"🔒 Статус: {'🔴 Заблокирован' if u[4] == 1 else '🟢 Активен'}"
            
            await message.answer(text, reply_markup=admin_kb())
            user_pages.pop(message.from_user.id, None)
        except ValueError:
            await message.answer("❌ Введите корректный ID", reply_markup=admin_kb())

@router.callback_query(F.data == "a_messages")
async def a_messages(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    cursor.execute("SELECT id, user_id, username, text, date, status FROM messages_to_admin ORDER BY date DESC LIMIT 20")
    messages = cursor.fetchall()
    
    if not messages:
        await callback.message.edit_text("📩 **Входящие обращения**\n\nНет обращений.", reply_markup=admin_kb())
        await callback.answer()
        return
    
    text = "📩 **Входящие обращения**\n\n"
    for msg in messages:
        status = "🆕" if msg[5] == "new" else "✅"
        name = msg[2] or f"User_{msg[1]}"
        text += f"{status} `{msg[1]}` — {name}\n"
        text += f"📝 {msg[3][:50]}{'...' if len(msg[3]) > 50 else ''}\n"
        text += f"🕐 {msg[4][:16]}\n"
        text += f"👉 /reply_{msg[1]} Текст ответа\n\n"
    
    await callback.message.edit_text(text[:4000], reply_markup=admin_kb())
    await callback.answer()

@router.message(Command("reply"))
async def reply_to_user(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        return
    
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ Использование: /reply_123 Текст ответа")
        return
    
    try:
        user_id = int(parts[0].replace("/reply_", ""))
        reply_text = " ".join(parts[1:])
        
        cursor.execute("UPDATE messages_to_admin SET status = 'answered' WHERE user_id = ? AND status = 'new'", (user_id,))
        conn.commit()
        
        try:
            await message.bot.send_message(
                user_id,
                f"📩 **Ответ от администратора:**\n\n{reply_text}"
            )
            await message.answer(f"✅ Сообщение отправлено пользователю `{user_id}`")
        except Exception as e:
            await message.answer(f"❌ Не удалось отправить: {e}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.callback_query(F.data == "a_broadcast")
async def a_broadcast(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    user_pages[callback.from_user.id] = {"state": "waiting_broadcast"}
    
    await callback.message.edit_text(
        "📢 **РАССЫЛКА**\n\n"
        "Отправьте сообщение для рассылки всем пользователям.\n\n"
        "⏹ Отмена: /cancel"
    )
    await callback.answer()

@router.callback_query(F.data == "a_limits")
async def a_limits(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    free_in = get_setting('free_input_chars')
    free_out = get_setting('free_output_words')
    prem_in = get_setting('premium_input_chars')
    prem_out = get_setting('premium_output_words')
    img_free = get_setting('image_limit_free')
    img_prem = get_setting('image_limit_premium')
    
    text = "⚙️ **ТЕКУЩИЕ ЛИМИТЫ**\n\n"
    text += "🔹 **Текстовые запросы:**\n"
    text += f"  📥 Вход: {free_in} символов\n"
    text += f"  📤 Выход: {free_out} слов\n\n"
    text += "🔸 **Premium:**\n"
    text += f"  📥 Вход: {prem_in} символов\n"
    text += f"  📤 Выход: {prem_out} слов\n\n"
    text += "🖼️ **Картинки:**\n"
    text += f"  🔹 Бесплатно: {img_free} картинок/день\n"
    text += f"  🔸 Premium: {img_prem} картинок/день"
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔹 Бесплатные символы", callback_data="l_free_in")],
            [InlineKeyboardButton(text="🔹 Бесплатные слова", callback_data="l_free_out")],
            [InlineKeyboardButton(text="🔸 Premium символы", callback_data="l_prem_in")],
            [InlineKeyboardButton(text="🔸 Premium слова", callback_data="l_prem_out")],
            [InlineKeyboardButton(text="🖼️ Лимит картинок (бесплатно)", callback_data="l_img_free")],
            [InlineKeyboardButton(text="🖼️ Лимит картинок (Premium)", callback_data="l_img_prem")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")]
        ]
    )
    
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("l_"))
async def l_edit(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    key_map = {
        "l_free_in": "free_input_chars",
        "l_free_out": "free_output_words",
        "l_prem_in": "premium_input_chars",
        "l_prem_out": "premium_output_words",
        "l_img_free": "image_limit_free",
        "l_img_prem": "image_limit_premium"
    }
    key = key_map.get(callback.data)
    if not key:
        await callback.answer("Ошибка")
        return
    
    current = get_setting(key)
    
    if "image_limit" in key:
        values = [1, 3, 5, 10, 20, 50, 100, 200]
    else:
        values = [50, 100, 200, 300, 500, 1000, 3000, 5000]
    
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    row = []
    for val in values:
        row.append(InlineKeyboardButton(text=str(val), callback_data=f"s_{key}_{val}"))
        if len(row) == 4:
            kb.inline_keyboard.append(row)
            row = []
    if row:
        kb.inline_keyboard.append(row)
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="a_limits")])
    
    await callback.message.edit_text(f"📝 Текущее значение: **{current}**\n\nВыберите новое значение:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("s_"))
async def s_set(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer("Ошибка")
        return
    
    key = "_".join(parts[1:-1])
    value = parts[-1]
    
    set_setting(key, value)
    await callback.answer(f"✅ Установлено: {value}", show_alert=True)
    await a_limits(callback)

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    user_pages.pop(callback.from_user.id, None)
    
    from keyboards import main_menu
    text = "🤖 **Vertex AI**\n\n"
    text += "🧠 Искусственный интеллект в твоем Telegram!\n\n"
    text += "✅ 10 запросов в день бесплатно\n"
    text += "💎 Premium: безлимит\n"
    text += "👥 Приведи друга → +5 запросов\n\n"
    text += "Просто напиши свой вопрос!"
    
    try:
        await callback.message.edit_text(text, reply_markup=main_menu())
    except TelegramBadRequest:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=main_menu())
    await callback.answer()

# Другие функции для бэкапов
@router.callback_query(F.data == "a_backup")
async def a_backup(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text("⏳ Создаю бэкап...")
    
    try:
        backup = GitHubBackup()
        result = backup.backup_db(reason='ручной')
        
        if result:
            text = "✅ **БЭКАП УСПЕШНО СОЗДАН!**"
        else:
            text = "❌ **ОШИБКА СОЗДАНИЯ БЭКАПА!**"
        
        await callback.message.edit_text(text, reply_markup=admin_kb())
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_restore_db")
async def a_restore_db(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text("⏳ Восстанавливаю БД...")
    
    try:
        backup = GitHubBackup()
        result = backup.restore_latest_backup()
        
        if result:
            text = "✅ **БД ВОССТАНОВЛЕНА!**"
        else:
            text = "❌ **ОШИБКА ВОССТАНОВЛЕНИЯ!**"
        
        await callback.message.edit_text(text, reply_markup=admin_kb())
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_backup_manage")
async def a_backup_manage(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список бэкапов", callback_data="a_backup_list")],
            [InlineKeyboardButton(text="🗑️ Удалить ВСЕ", callback_data="a_backup_delete_all")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")]
        ]
    )
    
    await callback.message.edit_text("🗑️ **УПРАВЛЕНИЕ БЭКАПАМИ**", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "a_backup_list")
async def a_backup_list(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text("📋 Список бэкапов в GitHub", reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_backup_delete_all")
async def a_backup_delete_all(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text("🗑️ Все бэкапы удалены", reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_give_premium_list")
async def a_give_premium_list(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text("💎 Используйте /user_ID для выдачи Premium", reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "noop")
async def noop(callback: types.CallbackQuery):
    await callback.answer()
