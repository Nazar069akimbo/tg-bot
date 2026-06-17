from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import get_user
from keyboards import main_menu

router = Router()

@router.message(Command("profile"))
async def profile_cmd(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Напиши /start")
        return
    
    premium = user[3][:10] if user[3] else "нет"
    text = f"👤 **Профиль**\n\n"
    text += f"🆔 ID: {user[0]}\n"
    text += f"📆 Регистрация: {user[2][:10]}\n"
    text += f"📊 Решено: {user[5] or 0}\n"
    text += f"💎 Premium до: {premium}\n"
    text += f"🎯 Режим: {'📚 ГДЗ' if user[7] == 'gdz' else '💬 Общение'}"
    
    await message.answer(text, reply_markup=main_menu())

@router.callback_query(F.data == "profile")
async def profile_callback(callback: types.CallbackQuery):
    try:
        user = get_user(callback.from_user.id)
        if not user:
            await callback.message.edit_text("Напиши /start")
            await callback.answer()
            return
        
        premium = user[3][:10] if user[3] else "нет"
        text = f"👤 **Профиль**\n\n"
        text += f"🆔 ID: {user[0]}\n"
        text += f"📆 Регистрация: {user[2][:10]}\n"
        text += f"📊 Решено: {user[5] or 0}\n"
        text += f"💎 Premium до: {premium}\n"
        text += f"🎯 Режим: {'📚 ГДЗ' if user[7] == 'gdz' else '💬 Общение'}"
        
        await callback.message.edit_text(text, reply_markup=main_menu())
        await callback.answer()
    except Exception as e:
        await callback.answer()
