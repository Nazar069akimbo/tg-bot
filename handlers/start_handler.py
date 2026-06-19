from aiogram import Router, types
from aiogram.filters import Command
from database.db import create_user, get_user, add_referral
from keyboards import main_menu
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    logger.info(f"Start command from {user_id}")
    logger.info(f"Full message: {message.text}")
    
    if not user:
        create_user(user_id, message.from_user.username or "")
        logger.info(f"New user registered: {user_id}")
        
        # Обработка реферала
        args = message.text.split()
        logger.info(f"Args: {args}")
        
        if len(args) > 1:
            try:
                ref_id = int(args[1])
                logger.info(f"Referral ID: {ref_id}")
                
                if ref_id != user_id:
                    # Проверяем, существует ли реферер
                    ref_user = get_user(ref_id)
                    if ref_user:
                        add_referral(ref_id, user_id)
                        await message.answer("👤 Вы были приглашены! Реферер получил +5 запросов.")
                        logger.info(f"Referral: {ref_id} -> {user_id}")
                    else:
                        logger.warning(f"Referrer {ref_id} not found")
                else:
                    logger.warning(f"User tried to refer themselves: {user_id}")
            except ValueError as e:
                logger.warning(f"Invalid referral ID: {args[1]}")
            except Exception as e:
                logger.error(f"Error processing referral: {e}")
    else:
        logger.info(f"Existing user: {user_id}")
    
    await message.answer(
        "🤖 **Vertex AI**\n\n"
        "🧠 Искусственный интеллект в твоем Telegram!\n\n"
        "✅ 10 запросов в день бесплатно\n"
        "💎 Premium: безлимит\n"
        "👥 Приведи друга → +5 запросов\n\n"
        "Просто напиши свой вопрос!",
        reply_markup=main_menu()
    )
