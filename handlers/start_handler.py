from aiogram import Router, types
from aiogram.filters import Command
from database.db import create_user, get_user, add_referral, cursor
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
    
    args = message.text.split()
    referrer_id = None
    
    if len(args) > 1:
        try:
            referrer_id = int(args[1])
            logger.info(f"Referral ID from link: {referrer_id}")
        except:
            pass
    
    if not user:
        create_user(user_id, message.from_user.username or "")
        logger.info(f"New user registered: {user_id}")
        
        # Обработка реферала
        if referrer_id and referrer_id != user_id:
            ref_user = get_user(referrer_id)
            if ref_user:
                add_referral(referrer_id, user_id)
                await message.answer("👤 Вы были приглашены! Реферер получил +5 запросов.")
                logger.info(f"Referral saved: {referrer_id} -> {user_id}")
            else:
                logger.warning(f"Referrer {referrer_id} not found")
        else:
            logger.info(f"No valid referral")
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
