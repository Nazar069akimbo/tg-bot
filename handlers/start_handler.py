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
    
    logger.info(f"📥 START from user_id={user_id}")
    
    user = get_user(user_id)
    args = message.text.split()
    referrer_id = None
    
    if len(args) > 1:
        try:
            referrer_id = int(args[1])
        except:
            pass
    
    if not user:
        create_user(user_id, username)
        cursor.execute("UPDATE users SET trial_start = ?, trial_used = 0, trial_active = 1 WHERE user_id = ?",
                      (datetime.now().isoformat(), user_id))
        conn.commit()
        
        if referrer_id and referrer_id != user_id:
            ref_user = get_user(referrer_id)
            if ref_user:
                add_referral(referrer_id, user_id)
    
    text = (
        "🤖 **Vertex AI**\n\n"
        "🧠 Искусственный интеллект в твоем Telegram!\n\n"
        "🎁 **Пробный период:** 2 дня, 5 картинок/день\n"
        "✅ 10 текстовых запросов/день\n"
        "💎 Premium: безлимит\n"
        "👥 Приведи друга → +5 запросов\n\n"
        "Просто напиши свой вопрос!"
    )
    
    await message.answer(text, reply_markup=main_menu())
    logger.info(f"✅ START sent to {user_id}")
