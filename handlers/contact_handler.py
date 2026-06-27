from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import get_user, cursor, conn
from keyboards import main_menu
import logging
from datetime import datetime
import os

router = Router()
logger = logging.getLogger(__name__)
user_pages = {}

@router.callback_query(F.data == "contact_admin")
async def contact_admin_start(callback: types.CallbackQuery):
    try:
        logger.info(f"Contact admin from {callback.from_user.id}")
        user = get_user(callback.from_user.id)
        if not user:
            await callback.answer("👋 Напишите /start для регистрации", show_alert=True)
            return
        
        # Убедимся, что таблица существует
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages_to_admin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            text TEXT,
            date TEXT,
            status TEXT DEFAULT 'new'
        )
        ''')
        conn.commit()
        
        user_pages[callback.from_user.id] = {"state": "waiting_contact"}
        await callback.message.edit_text(
            "📩 **Обращение к администратору**\n\n"
            "Напишите ваше пожелание, вопрос или обращение.\n\n"
            "Я передам его администратору, и он ответит вам.\n\n"
            "⏹ Отмена: /cancel",
            reply_markup=main_menu()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Contact admin error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.message(F.text)
async def handle_contact(message: types.Message):
    try:
        user_id = message.from_user.id
        state = user_pages.get(user_id, {})
        if state.get("state") != "waiting_contact":
            return
        
        if message.text == "/cancel":
            user_pages.pop(user_id, None)
            await message.answer("✅ Отменено", reply_markup=main_menu())
            return
        
        user = get_user(user_id)
        username = user[1] if user else message.from_user.username or "без имени"
        
        cursor.execute(
            "INSERT INTO messages_to_admin (user_id, username, text, date, status) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, message.text, datetime.now().isoformat(), "new")
        )
        conn.commit()
        user_pages.pop(user_id, None)
        
        # Уведомление админу
        admin_id = int(os.getenv('ADMIN_ID', 6957852385))
        try:
            await message.bot.send_message(
                admin_id,
                f"📩 **Новое обращение!**\n\n"
                f"👤 Пользователь: `{user_id}`\n"
                f"👤 Имя: {username}\n"
                f"📝 Текст:\n{message.text}\n\n"
                f"Ответь через команду: /reply_{user_id} Текст ответа"
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление админу: {e}")
        
        await message.answer(
            "✅ **Ваше обращение отправлено администратору!**\n\n"
            "Ожидайте ответа.",
            reply_markup=main_menu()
        )
    except Exception as e:
        logger.error(f"Contact handler error: {e}")
        await message.answer("❌ Ошибка при отправке. Попробуйте позже.", reply_markup=main_menu())

@router.message(Command("cancel"))
async def cancel_cmd(message: types.Message):
    user_pages.pop(message.from_user.id, None)
    await message.answer("✅ Отменено", reply_markup=main_menu())
