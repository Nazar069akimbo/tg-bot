from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import create_user, get_user, cursor, conn
from keyboards import main_menu

router = Router()

@router.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if not user:
        create_user(user_id, message.from_user.username or "")
        
        # Обработка реферала
        args = message.text.split()
        if len(args) > 1:
            try:
                ref_id = int(args[1])
                if ref_id != user_id:
                    # Добавляем +5 задач рефереру
                    cursor.execute("UPDATE users SET free_requests = free_requests + 5 WHERE user_id = ?", (ref_id,))
                    conn.commit()
                    await message.answer("👤 Вы были приглашены! Реферер получил +5 задач.")
            except:
                pass
    
    await message.answer(
        "🚀 **Флагман Решебник**\n\n"
        "✅ 10 задач в день бесплатно\n"
        "💎 Premium: безлимит\n"
        "👥 Приведи друга → +5 задач\n\n"
        "Выбери режим:",
        reply_markup=main_menu()
    )
