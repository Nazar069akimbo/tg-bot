from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import get_user, can_request, is_premium, get_image_stats, get_trial_remaining
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("stats"))
async def stats_cmd(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Вы не зарегистрированы!\n\nНажмите /start")
        return
    
    ok, remaining = can_request(message.from_user.id)
    premium = is_premium(message.from_user.id)
    
    used, limit, is_prem = get_image_stats(message.from_user.id)
    trial_remaining = get_trial_remaining(message.from_user.id)
    
    status = "💎 Premium" if premium else "🔴 Бесплатный"
    mode = "📚 ГДЗ" if user[7] == "gdz" else "💬 Общение"
    
    text = f"📊 **Статистика**\n\n"
    text += f"📝 Текстовых запросов осталось: {remaining if not premium else '∞'}\n"
    text += f"🖼️ Картинок сегодня: {used}/{limit}\n"
    if trial_remaining > 0 and not premium:
        text += f"🎁 Пробный период: {trial_remaining} картинок осталось\n"
    text += f"💎 Статус: {status}\n"
    text += f"🎯 Режим: {mode}"
    
    await message.answer(text)

@router.callback_query(F.data == "stats")
async def stats_callback(callback: types.CallbackQuery):
    try:
        logger.info(f"Stats callback from {callback.from_user.id}")
        
        user = get_user(callback.from_user.id)
        if not user:
            await callback.message.edit_text("❌ Вы не зарегистрированы!\n\nНажмите /start")
            await callback.answer()
            return
        
        ok, remaining = can_request(callback.from_user.id)
        premium = is_premium(callback.from_user.id)
        
        used, limit, is_prem = get_image_stats(callback.from_user.id)
        trial_remaining = get_trial_remaining(callback.from_user.id)
        
        status = "💎 Premium" if premium else "🔴 Бесплатный"
        mode = "📚 ГДЗ" if user[7] == "gdz" else "💬 Общение"
        
        text = f"📊 **Статистика**\n\n"
        text += f"📝 Текстовых запросов осталось: {remaining if not premium else '∞'}\n"
        text += f"🖼️ Картинок сегодня: {used}/{limit}\n"
        if trial_remaining > 0 and not premium:
            text += f"🎁 Пробный период: {trial_remaining} картинок осталось\n"
        text += f"💎 Статус: {status}\n"
        text += f"🎯 Режим: {mode}"
        
        await callback.message.edit_text(text)
        await callback.answer()
    except Exception as e:
        logger.error(f"Stats callback error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
