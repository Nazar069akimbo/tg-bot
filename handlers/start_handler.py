from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import create_user, get_user, cursor, conn
from keyboards import main_menu
import logging
from backup_github import GitHubBackup

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    logger.info(f"Start command from {user_id}: {message.text}")
    args = message.text.split()
    
    # Если пользователь НЕ зарегистрирован — регистрируем
    if not user:
        create_user(user_id, message.from_user.username or "")
        logger.info(f"New user registered: {user_id}")
        
        # ========== БЭКАП ПРИ НОВОМ ПОЛЬЗОВАТЕЛЕ ==========
        try:
            backup = GitHubBackup()
            backup.backup_db(reason='новый пользователь')
            logger.info(f"✅ Бэкап сделан после регистрации пользователя {user_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка бэкапа: {e}")
        # ===================================================
        
        # Обработка реферала
        if len(args) > 1:
            try:
                ref_id = int(args[1])
                if ref_id != user_id:
                    ref_user = get_user(ref_id)
                    if ref_user:
                        cursor.execute("UPDATE users SET free_requests = free_requests + 5 WHERE user_id = ?", (ref_id,))
                        conn.commit()
                        logger.info(f"Added 5 free requests to referrer {ref_id}")
                        await message.answer("👤 Вы были приглашены! Реферер получил +5 задач.")
                    else:
                        logger.warning(f"Referrer {ref_id} not found")
                else:
                    logger.warning(f"User tried to refer themselves: {user_id}")
            except ValueError as e:
                logger.warning(f"Invalid referral ID: {args[1]}")
            except Exception as e:
                logger.error(f"Error processing referral: {e}")
    
    # ====== ВСЕГДА ПОКАЗЫВАЕМ ПРИВЕТСТВИЕ ======
    await message.answer(
        "🚀 **Флагман Решебник**\n\n"
        "✅ 10 задач в день бесплатно\n"
        "💎 Premium: безлимит\n"
        "👥 Приведи друга → +5 задач\n\n"
        "Выбери режим:",
        reply_markup=main_menu()
    )
    logger.info(f"Welcome message sent to {user_id}")
