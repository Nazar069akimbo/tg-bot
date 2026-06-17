from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import cursor

router = Router()

@router.message(Command("leaderboard"))
async def leaderboard_cmd(message: types.Message):
    cursor.execute("SELECT user_id, username, total_requests FROM users ORDER BY total_requests DESC LIMIT 10")
    users = cursor.fetchall()
    
    if not users:
        await message.answer("🏆 Пока нет данных")
        return
    
    text = "🏆 **Рейтинг**\n\n"
    medals = ["🥇", "🥈", "🥉"]
    
    for i, u in enumerate(users, 1):
        medal = medals[i-1] if i <= 3 else f"{i}."
        text += f"{medal} `{u[0]}` — {u[1] or 'без имени'} — {u[2]} задач\n"
    
    await message.answer(text)

@router.callback_query(F.data == "leaderboard")
async def leaderboard_callback(callback: types.CallbackQuery):
    try:
        cursor.execute("SELECT user_id, username, total_requests FROM users ORDER BY total_requests DESC LIMIT 10")
        users = cursor.fetchall()
        
        if not users:
            await callback.message.edit_text("🏆 Пока нет данных")
            await callback.answer()
            return
        
        text = "🏆 **Рейтинг**\n\n"
        medals = ["🥇", "🥈", "🥉"]
        
        for i, u in enumerate(users, 1):
            medal = medals[i-1] if i <= 3 else f"{i}."
            text += f"{medal} `{u[0]}` — {u[1] or 'без имени'} — {u[2]} задач\n"
        
        await callback.message.edit_text(text)
        await callback.answer()
    except Exception as e:
        await callback.answer()
