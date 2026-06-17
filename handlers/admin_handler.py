from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from database.db import is_admin, add_admin, cursor, conn, get_setting, set_setting, get_user
import asyncio
from datetime import datetime

router = Router()
ADMIN_CODE = "30121979"

# Временное хранилище для состояний
user_pages = {}

def admin_kb():
    """Главное меню админа"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="a_stats")],
            [InlineKeyboardButton(text="👥 Управление пользователями", callback_data="a_users_list")],
            [InlineKeyboardButton(text="⚙️ Лимиты", callback_data="a_limits")],
            [InlineKeyboardButton(text="📢 Рассылка", callback_data="a_broadcast")],
            [InlineKeyboardButton(text="💎 Выдать Premium", callback_data="a_give_premium_list")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ]
    )

def user_management_kb(page=0, total_pages=1):
    """Клавиатура управления пользователями"""
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"users_page_{page-1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"📄 {page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"users_page_{page+1}"))
    
    if nav_buttons:
        kb.inline_keyboard.append(nav_buttons)
    
    kb.inline_keyboard.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")
    ])
    
    return kb

def user_actions_kb(user_id):
    """Клавиатура действий с пользователем"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔴 Заблокировать", callback_data=f"block_user_{user_id}")],
            [InlineKeyboardButton(text="🟢 Разблокировать", callback_data=f"unblock_user_{user_id}")],
            [InlineKeyboardButton(text="💎 Выдать Premium", callback_data=f"give_premium_user_{user_id}")],
            [InlineKeyboardButton(text="📊 Статистика пользователя", callback_data=f"user_stats_{user_id}")],
            [InlineKeyboardButton(text="🔙 Назад к списку", callback_data="a_users_list")]
        ]
    )

def premium_days_kb(user_id):
    """Клавиатура выбора дней Premium"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="7 дней", callback_data=f"premium_days_{user_id}_7")],
            [InlineKeyboardButton(text="30 дней", callback_data=f"premium_days_{user_id}_30")],
            [InlineKeyboardButton(text="90 дней", callback_data=f"premium_days_{user_id}_90")],
            [InlineKeyboardButton(text="180 дней", callback_data=f"premium_days_{user_id}_180")],
            [InlineKeyboardButton(text="365 дней", callback_data=f"premium_days_{user_id}_365")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data=f"back_to_user_{user_id}")]
        ]
    )

def users_list_kb(users, page=0, total_pages=1):
    """Клавиатура со списком пользователей для выдачи Premium"""
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    
    for u in users:
        user_id = u[0]
        name = u[1] or f"User_{user_id}"
        if len(name) > 20:
            name = name[:18] + "..."
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=f"👤 {name} (ID: {user_id})", callback_data=f"select_user_{user_id}")
        ])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"premium_page_{page-1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"📄 {page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"premium_page_{page+1}"))
    
    if nav_buttons:
        kb.inline_keyboard.append(nav_buttons)
    
    kb.inline_keyboard.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")
    ])
    
    return kb

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
    text += f"👥 Всего пользователей: {total}\n"
    text += f"💎 Premium: {premium}\n"
    text += f"🔴 Заблокировано: {blocked}\n"
    text += f"📝 Всего запросов: {req}\n"
    text += f"🛡️ Администраторов: {admins}"
    
    try:
        await callback.message.edit_text(text, reply_markup=admin_kb())
    except TelegramBadRequest:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_users_list")
async def a_users_list(callback: types.CallbackQuery, page=0):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    per_page = 10
    offset = page * per_page
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    total_pages = (total_users + per_page - 1) // per_page
    
    cursor.execute("""
        SELECT user_id, username, total_requests, is_blocked, premium_until 
        FROM users 
        ORDER BY user_id 
        LIMIT ? OFFSET ?
    """, (per_page, offset))
    users = cursor.fetchall()
    
    text = "👥 **УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ**\n\n"
    if not users:
        text = "👥 Пользователей не найдено"
    else:
        for u in users:
            status = "🔴 Заблокирован" if u[3] == 1 else "🟢 Активен"
            premium = "💎" if u[4] and u[4] > datetime.now().isoformat() else "🔴"
            name = u[1] or "без имени"
            text += f"🆔 `{u[0]}` — {name}\n"
            text += f"   {status} | {premium} Задач: {u[2]}\n"
            text += f"   👉 Нажмите /user_{u[0]}\n\n"
    
    kb = user_management_kb(page, total_pages)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("users_page_"))
async def users_page(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    page = int(callback.data.split("_")[2])
    await a_users_list(callback, page)

@router.message(F.text.startswith("/user_"))
async def user_info_command(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        return
    
    try:
        user_id = int(message.text.replace("/user_", ""))
        await show_user_info(message, user_id)
    except ValueError:
        await message.answer("❌ Неверный ID пользователя")

@router.callback_query(F.data.startswith("user_stats_"))
async def user_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[2])
    await show_user_info(callback, user_id)
    await callback.answer()

async def show_user_info(target, user_id):
    """Показать информацию о пользователе"""
    user = get_user(user_id)
    if not user:
        if isinstance(target, types.Message):
            await target.answer("❌ Пользователь не найден")
        else:
            await target.answer("❌ Пользователь не найден")
        return
    
    cursor.execute("SELECT username, joined, premium_until, free_requests, total_requests, is_blocked, mode FROM users WHERE user_id = ?", (user_id,))
    u = cursor.fetchone()
    
    premium_status = "✅ Активен" if u[2] and u[2] > datetime.now().isoformat() else "❌ Не активен"
    premium_until = u[2][:10] if u[2] else "Нет"
    block_status = "🔴 Заблокирован" if u[5] == 1 else "🟢 Активен"
    mode = "📚 ГДЗ" if u[6] == "gdz" else "💬 Общение"
    
    text = f"👤 **ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ**\n\n"
    text += f"🆔 ID: `{user_id}`\n"
    text += f"👤 Имя: {u[0] or 'без имени'}\n"
    text += f"📆 Регистрация: {u[1][:10] if u[1] else 'Нет'}\n"
    text += f"📊 Решено задач: {u[4] or 0}\n"
    text += f"🎯 Режим: {mode}\n"
    text += f"💎 Premium: {premium_status}\n"
    text += f"📅 Premium до: {premium_until}\n"
    text += f"🔒 Статус: {block_status}"
    
    kb = user_actions_kb(user_id)
    
    if isinstance(target, types.Message):
        await target.answer(text, reply_markup=kb)
    else:
        try:
            await target.message.edit_text(text, reply_markup=kb)
        except TelegramBadRequest:
            await target.message.delete()
            await target.message.answer(text, reply_markup=kb)

@router.callback_query(F.data.startswith("block_user_"))
async def block_user(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[2])
    
    if is_admin(user_id):
        await callback.answer("❌ Нельзя заблокировать администратора!", show_alert=True)
        return
    
    cursor.execute("UPDATE users SET is_blocked = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    
    await callback.answer(f"✅ Пользователь {user_id} заблокирован", show_alert=True)
    await show_user_info(callback, user_id)

@router.callback_query(F.data.startswith("unblock_user_"))
async def unblock_user(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[2])
    cursor.execute("UPDATE users SET is_blocked = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    
    await callback.answer(f"✅ Пользователь {user_id} разблокирован", show_alert=True)
    await show_user_info(callback, user_id)

@router.callback_query(F.data.startswith("give_premium_user_"))
async def give_premium_user(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[3])
    
    text = f"💎 **ВЫБЕРИТЕ ПЕРИОД PREMIUM**\n\n"
    text += f"Для пользователя: `{user_id}`\n\n"
    text += "Выберите количество дней:"
    
    try:
        await callback.message.edit_text(text, reply_markup=premium_days_kb(user_id))
    except TelegramBadRequest:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=premium_days_kb(user_id))
    await callback.answer()

@router.callback_query(F.data.startswith("premium_days_"))
async def premium_days_set(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    parts = callback.data.split("_")
    user_id = int(parts[2])
    days = int(parts[3])
    
    from database.db import add_premium
    add_premium(user_id, days)
    
    user_pages.pop(callback.from_user.id, None)
    
    try:
        await callback.bot.send_message(
            user_id,
            f"🎉 Администратор выдал вам Premium на {days} дней!\n\n"
            f"Теперь у вас безлимит задач и 3000 символов на запрос."
        )
    except:
        pass
    
    await callback.answer(f"✅ Premium выдан пользователю {user_id} на {days} дней", show_alert=True)
    await show_user_info(callback, user_id)

@router.callback_query(F.data.startswith("back_to_user_"))
async def back_to_user(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[3])
    await show_user_info(callback, user_id)
    await callback.answer()

@router.callback_query(F.data == "a_give_premium_list")
async def a_give_premium_list(callback: types.CallbackQuery, page=0):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    per_page = 10
    offset = page * per_page
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    total_pages = (total_users + per_page - 1) // per_page
    
    cursor.execute("""
        SELECT user_id, username, total_requests 
        FROM users 
        ORDER BY user_id 
        LIMIT ? OFFSET ?
    """, (per_page, offset))
    users = cursor.fetchall()
    
    text = "💎 **ВЫДАТЬ PREMIUM**\n\n"
    text += "Выберите пользователя из списка:\n\n"
    
    if not users:
        text = "👥 Пользователей не найдено"
    else:
        for u in users:
            name = u[1] or "без имени"
            text += f"🆔 `{u[0]}` — {name} — {u[2]} задач\n"
    
    kb = users_list_kb(users, page, total_pages)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("premium_page_"))
async def premium_page(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    page = int(callback.data.split("_")[2])
    await a_give_premium_list(callback, page)

@router.callback_query(F.data.startswith("select_user_"))
async def select_user_for_premium(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[2])
    
    user = get_user(user_id)
    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    
    text = f"💎 **ВЫБЕРИТЕ ПЕРИОД PREMIUM**\n\n"
    text += f"Для пользователя: `{user_id}`\n\n"
    text += "Выберите количество дней:"
    
    try:
        await callback.message.edit_text(text, reply_markup=premium_days_kb(user_id))
    except TelegramBadRequest:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=premium_days_kb(user_id))
    await callback.answer()

# ============ РАССЫЛКА (упрощенная версия) ============

@router.callback_query(F.data == "a_broadcast")
async def a_broadcast(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    text = "📢 **РАССЫЛКА**\n\n"
    text += "Просто отправьте сообщение, которое хотите разослать ВСЕМ пользователям.\n\n"
    text += "⏹ Чтобы отменить, отправьте /cancel"
    
    # Сохраняем состояние
    user_pages[callback.from_user.id] = {"state": "waiting_broadcast"}
    
    try:
        await callback.message.edit_text(text)
    except TelegramBadRequest:
        await callback.message.delete()
        await callback.message.answer(text)
    await callback.answer()

@router.message(F.text)
async def handle_broadcast(message: types.Message):
    # Проверяем, что это админ и он в режиме рассылки
    if not is_admin(message.from_user.id):
        return
    
    state = user_pages.get(message.from_user.id, {})
    if state.get("state") != "waiting_broadcast":
        return
    
    # Отмена
    if message.text == "/cancel":
        user_pages.pop(message.from_user.id, None)
        await message.answer("✅ Рассылка отменена", reply_markup=admin_kb())
        return
    
    # Нельзя отправлять команды
    if message.text.startswith("/"):
        await message.answer("❌ Нельзя использовать команды в тексте рассылки")
        return
    
    # Получаем текст для рассылки
    broadcast_text = message.text
    
    # Получаем всех пользователей
    cursor.execute("SELECT user_id FROM users WHERE is_blocked = 0")
    users = cursor.fetchall()
    
    if not users:
        await message.answer("❌ Нет активных пользователей для рассылки")
        user_pages.pop(message.from_user.id, None)
        return
    
    # Подтверждение
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Отправить всем", callback_data=f"confirm_broadcast")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_broadcast")]
        ]
    )
    
    await message.answer(
        f"📢 **ПОДТВЕРЖДЕНИЕ РАССЫЛКИ**\n\n"
        f"👥 Получателей: {len(users)}\n\n"
        f"📝 Текст:\n"
        f"`{broadcast_text[:300]}{'...' if len(broadcast_text) > 300 else ''}`\n\n"
        f"Отправить?",
        reply_markup=kb
    )
    
    # Сохраняем текст для рассылки
    user_pages[message.from_user.id] = {
        "state": "confirm_broadcast", 
        "text": broadcast_text,
        "users": users
    }

@router.callback_query(F.data == "cancel_broadcast")
async def cancel_broadcast(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    user_pages.pop(callback.from_user.id, None)
    try:
        await callback.message.delete()
    except:
        pass
    await callback.message.answer("✅ Рассылка отменена", reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "confirm_broadcast")
async def confirm_broadcast(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    data = user_pages.get(callback.from_user.id, {})
    broadcast_text = data.get("text", "")
    users = data.get("users", [])
    
    if not broadcast_text or not users:
        await callback.answer("❌ Ошибка: нет текста или пользователей", show_alert=True)
        return
    
    # Сразу отвечаем на callback
    await callback.answer("⏳ Начинаю рассылку...")
    
    # Удаляем сообщение с подтверждением
    try:
        await callback.message.delete()
    except:
        pass
    
    # Отправляем статус
    status_msg = await callback.message.answer(
        f"⏳ Начинаю рассылку...\n"
        f"👥 Всего: {len(users)}\n"
        f"📤 Отправлено: 0"
    )
    
    sent = 0
    failed = 0
    
    for i, u in enumerate(users, 1):
        try:
            await callback.bot.send_message(u[0], broadcast_text)
            sent += 1
            
            # Обновляем статус каждые 10 сообщений
            if i % 10 == 0:
                try:
                    await status_msg.edit_text(
                        f"⏳ Рассылка...\n"
                        f"👥 Всего: {len(users)}\n"
                        f"📤 Отправлено: {sent}\n"
                        f"❌ Ошибок: {failed}"
                    )
                except:
                    pass
                
            # Небольшая задержка, чтобы не превысить лимиты Telegram
            await asyncio.sleep(0.03)
            
        except Exception as e:
            failed += 1
    
    # Финальный результат
    final_text = f"✅ **РАССЫЛКА ЗАВЕРШЕНА**\n\n"
    final_text += f"📤 Отправлено: {sent}\n"
    final_text += f"❌ Не доставлено: {failed}\n"
    final_text += f"👥 Всего: {len(users)}"
    
    await status_msg.edit_text(final_text, reply_markup=admin_kb())
    
    # Очищаем состояние
    user_pages.pop(callback.from_user.id, None)

# ============ КОНЕЦ РАССЫЛКИ ============

@router.callback_query(F.data == "a_limits")
async def a_limits(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    free_in = get_setting('free_input_chars')
    free_out = get_setting('free_output_words')
    prem_in = get_setting('premium_input_chars')
    prem_out = get_setting('premium_output_words')
    
    text = "⚙️ **ТЕКУЩИЕ ЛИМИТЫ**\n\n"
    text += f"🔹 Бесплатные:\n"
    text += f"  📥 Вход: {free_in} символов\n"
    text += f"  📤 Выход: {free_out} слов\n\n"
    text += f"🔸 Premium:\n"
    text += f"  📥 Вход: {prem_in} символов\n"
    text += f"  📤 Выход: {prem_out} слов"
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔹 Бесплатные символы", callback_data="l_free_in")],
            [InlineKeyboardButton(text="🔹 Бесплатные слова", callback_data="l_free_out")],
            [InlineKeyboardButton(text="🔸 Premium символы", callback_data="l_prem_in")],
            [InlineKeyboardButton(text="🔸 Premium слова", callback_data="l_prem_out")],
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
        "l_prem_out": "premium_output_words"
    }
    key = key_map.get(callback.data)
    if not key:
        await callback.answer("Ошибка")
        return
    
    current = get_setting(key)
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="50", callback_data=f"s_{key}_50")],
            [InlineKeyboardButton(text="100", callback_data=f"s_{key}_100")],
            [InlineKeyboardButton(text="200", callback_data=f"s_{key}_200")],
            [InlineKeyboardButton(text="300", callback_data=f"s_{key}_300")],
            [InlineKeyboardButton(text="500", callback_data=f"s_{key}_500")],
            [InlineKeyboardButton(text="1000", callback_data=f"s_{key}_1000")],
            [InlineKeyboardButton(text="3000", callback_data=f"s_{key}_3000")],
            [InlineKeyboardButton(text="5000", callback_data=f"s_{key}_5000")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="a_limits")]
        ]
    )
    
    try:
        await callback.message.edit_text(f"📝 Текущее значение: **{current}**\n\nВыберите новое значение:", reply_markup=kb)
    except TelegramBadRequest:
        await callback.message.delete()
        await callback.message.answer(f"📝 Текущее значение: **{current}**\n\nВыберите новое значение:", reply_markup=kb)
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
    text = "🚀 **Флагман Решебник**\n\n"
    text += "✅ 10 задач в день бесплатно\n"
    text += "💎 Premium: безлимит\n"
    text += "👥 Приведи друга → +5 задач\n\n"
    text += "Выбери режим:"
    
    try:
        await callback.message.edit_text(text, reply_markup=main_menu())
    except TelegramBadRequest:
        await callback.message.delete()
        await callback.message.answer(text, reply_markup=main_menu())
    await callback.answer()

@router.callback_query(F.data == "noop")
async def noop(callback: types.CallbackQuery):
    await callback.answer()
