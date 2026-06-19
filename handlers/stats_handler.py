from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import get_user, can_request, is_premium

router = Router()

@router.message(Command("stats"))
async def stats_cmd(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer(
            "❌ Вы не зарегистрированы!\n\n"
            "Нажмите /start для регистрации."
        )
        return
    
    ok, remaining = can_request(message.from_user.id)
    premium = is_premium(message.from_user.id)
    status = "💎 Premium" if premium else "🔴 Бесплатный"
    
    text = f"📊 **Статистика**\n\n"
    text += f"📝 Запросов сделано: {user[5] or 0}\n"
    text += f"🎯 Осталось: {remaining}\n"
    text += f"💎 Статус: {status}"
    
    await message.answer(text)

@router.callback_query(F.data == "stats")
async def stats_callback(callback: types.CallbackQuery):
    try:
        user = get_user(callback.from_user.id)
        if not user:
            await callback.message.edit_text(
                "❌ Вы не зарегистрированы!\n\n"
                "Нажмите /start для регистрации."
            )
            await callback.answer()
            return
        
        ok, remaining = can_request(callback.from_user.id)
        premium = is_premium(callback.from_user.id)
        status = "💎 Premium" if premium else "🔴 Бесплатный"
        
        text = f"📊 **Статистика**\n\n"
        text += f"📝 Запросов сделано: {user[5] or 0}\n"
        text += f"🎯 Осталось: {remaining}\n"
        text += f"💎 Статус: {status}"
        
        await callback.message.edit_text(text)
        await callback.answer()
    except Exception as e:
        await callback.answer()
