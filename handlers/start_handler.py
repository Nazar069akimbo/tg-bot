from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import create_user, get_user, cursor, conn
from keyboards import main_menu
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    # Логируем все параметры для отладки
    logger.info(f"Start command from {user_id}: {message.text}")
    
    # Получаем аргументы команды /start
    args = message.text.split()
    logger.info(f"Args: {args}")
    
    # Если пользователь новый - регистрируем
    if not user:
        create_user(user_id, message.from_user.username or "")
        logger.info(f"New user registered: {user_id}")
        
        # Обработка реферала
        if len(args) > 1:
            try:
                ref_id = int(args[1])
                logger.info(f"Referral ID from args: {ref_id}")
                
                # Проверяем, что реферал не равен самому себе
                if ref_id != user_id:
                    # Проверяем, что реферер существует
                    ref_user = get_user(ref_id)
                    if ref_user:
                        # Добавляем +5 задач рефереру
                        cursor.execute("UPDATE users SET free_requests = free_requests + 5 WHERE user_id = ?", (ref_id,))
                        conn.commit()
                        logger.info(f"Added 5 free requests to referrer {ref_id}")
                        await message.answer("👤 Вы были приглашены! Реферер получил +5 задач.")
                    else:
                        logger.warning(f"Referrer {ref_id} not found")
                else:
                    logger.warning(f"User tried to refer themselves: {user_id}")
            except ValueError as e:
                logger.warning(f"Invalid referral ID: {args[1]}, error: {e}")
            except Exception as e:
                logger.error(f"Error processing referral: {e}")
        else:
            logger.info(f"No referral arguments for user {user_id}")
    else:
        logger.info(f"Existing user started bot: {user_id}")
    
    # Отправляем приветственное сообщение
    await message.answer(
        "🚀 **Флагман Решебник**\n\n"
        "✅ 10 задач в день бесплатно\n"
        "💎 Premium: безлимит\n"
        "👥 Приведи друга → +5 задач\n\n"
        "Выбери режим:",
        reply_markup=main_menu()
    )
