from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import get_user, cursor, conn
from keyboards import main_menu
import logging
from datetime import datetime

router = Router()
logger = logging.getLogger(__name__)

# Временное хранилище для состояний
user_pages = {}

@router.callback_query(F.data == "contact_admin")
async def contact_admin_start(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        await callback.answer("👋 Напишите /start для регистрации", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📩 **Обращение к администратору**\n\n"
        "Напишите ваше пожелание, вопрос или обращение.\n\n"
        "Я передам его администратору, и он ответит вам.\n\n"
        "⏹ Отмена: /cancel"
    )
    user_pages[callback.from_user.id] = {"state": "waiting_contact"}
    await callback.answer()

@router.message(F.text)
async def handle_contact(message: types.Message):
    user_id = message.from_user.id
    state = user_pages.get(user_id, {})
    
    if state.get("state") != "waiting_contact":
        return
    
    if message.text == "/cancel":
        user_pages.pop(user_id, None)
        await message.answer("✅ Отменено", reply_markup=main_menu())
        return
    
    # Сохраняем обращение в БД
    try:
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
        
        user = get_user(user_id)
        username = user[1] if user else "без имени"
        
        cursor.execute(
            "INSERT INTO messages_to_admin (user_id, username, text, date) VALUES (?, ?, ?, ?)",
            (user_id, username, message.text, datetime.now().isoformat())
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
                f"📝 Текст:\n{message.text}\n\n"
                f"Ответь через команду: /reply_{user_id}"
            )
        except:
            pass
        
        await message.answer(
            "✅ Ваше обращение отправлено администратору!\n\n"
            "Ожидайте ответа.",
            reply_markup=main_menu()
        )
    except Exception as e:
        logger.error(f"Error saving contact: {e}")
        await message.answer("❌ Ошибка при отправке. Попробуйте позже.")

@router.message(Command("reply"))
async def reply_to_user(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        return
    
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("❌ Использование: /reply_123 Текст ответа")
        return
    
    try:
        user_id = int(parts[0].replace("/reply_", ""))
        reply_text = " ".join(parts[1:])
        
        await message.bot.send_message(
            user_id,
            f"📩 **Ответ от администратора:**\n\n{reply_text}"
        )
        
        # Отмечаем обращение как обработанное
        cursor.execute("UPDATE messages_to_admin SET status = 'answered' WHERE user_id = ? AND status = 'new'", (user_id,))
        conn.commit()
        
        await message.answer(f"✅ Ответ отправлен пользователю `{user_id}`")
    except ValueError:
        await message.answer("❌ Неверный ID пользователя")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
