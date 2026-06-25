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
    user = get_user(user_id)
    
    args = message.text.split()
    referrer_id = None
    
    if len(args) > 1:
        try:
            referrer_id = int(args[1])
        except:
            pass
    
    if not user:
        create_user(user_id, message.from_user.username or "")
        
        cursor.execute("""
            UPDATE users 
            SET trial_start = ?, trial_used = 0, trial_active = 1 
            WHERE user_id = ?
        """, (datetime.now().isoformat(), user_id))
        conn.commit()
        logger.info(f"✅ Пробный период активирован для {user_id}")
        
        if referrer_id and referrer_id != user_id:
            ref_user = get_user(referrer_id)
            if ref_user:
                add_referral(referrer_id, user_id)
                await message.answer("👤 Вы были приглашены! Реферер получил +5 запросов.")
    
    await message.answer(
        "🤖 **Vertex AI**\n\n"
        "🧠 Искусственный интеллект в твоем Telegram!\n\n"
        "🎁 **Пробный период:**\n"
        "• 2 дня бесплатно\n"
        "• 5 картинок в день\n\n"
        "✅ 10 текстовых запросов/день\n"
        "💎 Premium: безлимит\n"
        "👥 Приведи друга → +5 запросов\n\n"
        "Просто напиши свой вопрос!",
        reply_markup=main_menu()
    )
