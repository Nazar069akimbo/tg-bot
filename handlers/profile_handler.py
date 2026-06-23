from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import get_user, cursor
from keyboards import main_menu

router = Router()

@router.message(Command("profile"))
async def profile_cmd(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer(
            "❌ Вы не зарегистрированы!\n\n"
            "Нажмите /start для регистрации.",
            reply_markup=main_menu()
        )
        return
    
    # Проверяем таблицу referrals
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='referrals'")
    if cursor.fetchone():
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (message.from_user.id,))
        referrals_count = cursor.fetchone()[0]
    else:
        referrals_count = 0
    
    premium = user[3][:10] if user[3] else "нет"
    text = f"👤 **Профиль**\n\n"
    text += f"🆔 ID: {user[0]}\n"
    text += f"📆 Регистрация: {user[2][:10]}\n"
    text += f"📊 Запросов: {user[5] or 0}\n"
    text += f"👥 Приглашено: {referrals_count}\n"
    text += f"💎 Premium до: {premium}"
    
    await message.answer(text, reply_markup=main_menu())

@router.callback_query(F.data == "profile")
async def profile_callback(callback: types.CallbackQuery):
    try:
        user = get_user(callback.from_user.id)
        if not user:
            await callback.message.edit_text(
                "❌ Вы не зарегистрированы!\n\n"
                "Нажмите /start для регистрации.",
                reply_markup=main_menu()
            )
            await callback.answer()
            return
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='referrals'")
        if cursor.fetchone():
            cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (callback.from_user.id,))
            referrals_count = cursor.fetchone()[0]
        else:
            referrals_count = 0
        
        premium = user[3][:10] if user[3] else "нет"
        text = f"👤 **Профиль**\n\n"
        text += f"🆔 ID: {user[0]}\n"
        text += f"📆 Регистрация: {user[2][:10]}\n"
        text += f"📊 Запросов: {user[5] or 0}\n"
        text += f"👥 Приглашено: {referrals_count}\n"
        text += f"💎 Premium до: {premium}"
        
        await callback.message.edit_text(text, reply_markup=main_menu())
        await callback.answer()
    except Exception as e:
        await callback.answer()
