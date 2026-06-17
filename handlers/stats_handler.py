from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import get_user, can_request, is_premium

router = Router()

@router.message(Command("stats"))
async def stats_cmd(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Напиши /start")
        return
    
    ok, remaining = can_request(message.from_user.id)
    premium = is_premium(message.from_user.id)
    status = "💎 Premium" if premium else "🔴 Бесплатный"
    mode = "📚 ГДЗ" if user[7] == "gdz" else "💬 Общение"
    
    text = f"📊 **Статистика**\n\n"
    text += f"📝 Решено: {user[5] or 0}\n"
    text += f"🎯 Осталось: {remaining}\n"
    text += f"💎 Статус: {status}\n"
    text += f"🎯 Режим: {mode}"
    
    await message.answer(text)

@router.callback_query(F.data == "stats")
async def stats_callback(callback: types.CallbackQuery):
    try:
        user = get_user(callback.from_user.id)
        if not user:
            await callback.message.edit_text("Напиши /start")
            await callback.answer()
            return
        
        ok, remaining = can_request(callback.from_user.id)
        premium = is_premium(callback.from_user.id)
        status = "💎 Premium" if premium else "🔴 Бесплатный"
        mode = "📚 ГДЗ" if user[7] == "gdz" else "💬 Общение"
        
        text = f"📊 **Статистика**\n\n"
        text += f"📝 Решено: {user[5] or 0}\n"
        text += f"🎯 Осталось: {remaining}\n"
        text += f"💎 Статус: {status}\n"
        text += f"🎯 Режим: {mode}"
        
        await callback.message.edit_text(text)
        await callback.answer()
    except Exception as e:
        await callback.answer()
