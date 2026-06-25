from aiogram import Router, types
from aiogram.filters import Command
from database.db import create_user, get_user, add_referral, cursor, conn
from keyboards import main_menu
import logging
from datetime import datetime

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    
    logger.info(f"📥 Start command from user_id={user_id}, username={username}")
    
    user = get_user(user_id)
    
    args = message.text.split()
    referrer_id = None
    
    if len(args) > 1:
        try:
            referrer_id = int(args[1])
            logger.info(f"🔗 Referral link detected: referrer_id={referrer_id}")
        except:
            pass
    
    if not user:
        logger.info(f"👤 New user: creating user_id={user_id}")
        create_user(user_id, username)
        
        cursor.execute("""
            UPDATE users 
            SET trial_start = ?, trial_used = 0, trial_active = 1 
            WHERE user_id = ?
        """, (datetime.now().isoformat(), user_id))
        conn.commit()
        logger.info(f"✅ Trial period activated for {user_id}")
        
        if referrer_id and referrer_id != user_id:
            ref_user = get_user(referrer_id)
            if ref_user:
                add_referral(referrer_id, user_id)
                logger.info(f"✅ Referral: {referrer_id} -> {user_id}")
                try:
                    await message.bot.send_message(
                        referrer_id,
                        f"🎉 По вашей ссылке зарегистрировался новый пользователь!\n"
                        f"Вам начислено +5 запросов."
                    )
                except:
                    pass
    else:
        logger.info(f"👤 Existing user: user_id={user_id}")
    
    text = (
        "🤖 **Vertex AI**\n\n"
        "🧠 Искусственный интеллект в твоем Telegram!\n\n"
        "🎁 **Пробный период:**\n"
        "• 2 дня бесплатно\n"
        "• 5 картинок в день\n\n"
        "✅ 10 текстовых запросов/день\n"
        "💎 Premium: безлимит\n"
        "👥 Приведи друга → +5 запросов\n\n"
        "Просто напиши свой вопрос!"
    )
    
    try:
        await message.answer(text, reply_markup=main_menu())
        logger.info(f"✅ Start message sent to user_id={user_id}")
    except Exception as e:
        logger.error(f"❌ Failed to send start message: {e}")
        await message.answer(text)
