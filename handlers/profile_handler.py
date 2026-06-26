from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import get_user, cursor, get_user_plan, get_image_stats, is_premium
from keyboards import main_menu

router = Router()

@router.message(Command("profile"))
async def profile_cmd(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Вы не зарегистрированы!\n\nНажмите /start", reply_markup=main_menu())
        return
    
    cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (message.from_user.id,))
    referrals_count = cursor.fetchone()[0] or 0
    
    plan = get_user_plan(message.from_user.id)
    premium = is_premium(message.from_user.id)
    
    # Статистика по картинкам
    used, limit, is_prem = get_image_stats(message.from_user.id)
    
    text = f"👤 **Профиль**\n\n"
    text += f"🆔 ID: {user[0]}\n"
    text += f"📆 Регистрация: {user[2][:10]}\n"
    text += f"📊 Запросов: {user[5] or 0}\n"
    text += f"👥 Приглашено: {referrals_count}\n"
    text += f"💎 Premium: {'✅ Активен' if premium else '❌ Нет'}\n"
    text += f"📊 План: {plan.upper()}\n"
    text += f"🖼️ Картинки: {used}/{limit} (сегодня)"
    
    await message.answer(text, reply_markup=main_menu())

@router.callback_query(F.data == "profile")
async def profile_callback(callback: types.CallbackQuery):
    try:
        user = get_user(callback.from_user.id)
        if not user:
            await callback.message.edit_text("❌ Вы не зарегистрированы!\n\nНажмите /start", reply_markup=main_menu())
            await callback.answer()
            return
        
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (callback.from_user.id,))
        referrals_count = cursor.fetchone()[0] or 0
        
        plan = get_user_plan(callback.from_user.id)
        premium = is_premium(callback.from_user.id)
        
        used, limit, is_prem = get_image_stats(callback.from_user.id)
        
        text = f"👤 **Профиль**\n\n"
        text += f"🆔 ID: {user[0]}\n"
        text += f"📆 Регистрация: {user[2][:10]}\n"
        text += f"📊 Запросов: {user[5] or 0}\n"
        text += f"👥 Приглашено: {referrals_count}\n"
        text += f"💎 Premium: {'✅ Активен' if premium else '❌ Нет'}\n"
        text += f"📊 План: {plan.upper()}\n"
        text += f"🖼️ Картинки: {used}/{limit} (сегодня)"
        
        await callback.message.edit_text(text, reply_markup=main_menu())
        await callback.answer()
    except Exception as e:
        await callback.answer()
