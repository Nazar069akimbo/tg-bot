from aiogram import Router, types, F
from aiogram.filters import Command
from keyboards import main_menu
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("help"))
async def help_cmd(message: types.Message):
    text = "❓ **Vertex AI — Помощь**\n\n"
    text += "🤖 **Что я умею:**\n"
    text += "• Отвечаю на любые вопросы\n"
    text += "• Помогаю с учебой\n"
    text += "• Решаю задачи\n"
    text += "• Генерирую картинки\n\n"
    text += "📋 **Команды:**\n"
    text += "/start — Главное меню\n"
    text += "/profile — Профиль\n"
    text += "/stats — Статистика\n"
    text += "/subscribe — Premium\n"
    text += "/referral — Рефералы\n\n"
    text += "💎 **Premium:**\n"
    text += "• Безлимит запросов\n"
    text += "• 50 картинок в день\n"
    text += "• Приоритетная обработка"
    await message.answer(text, reply_markup=main_menu())

@router.callback_query(F.data == "help")
async def help_callback(callback: types.CallbackQuery):
    try:
        logger.info(f"Help callback from {callback.from_user.id}")
        
        text = "❓ **Vertex AI — Помощь**\n\n"
        text += "🤖 **Что я умею:**\n"
        text += "• Отвечаю на любые вопросы\n"
        text += "• Помогаю с учебой\n"
        text += "• Решаю задачи\n"
        text += "• Генерирую картинки\n\n"
        text += "📋 **Команды:**\n"
        text += "/start — Главное меню\n"
        text += "/profile — Профиль\n"
        text += "/stats — Статистика\n"
        text += "/subscribe — Premium\n"
        text += "/referral — Рефералы\n\n"
        text += "💎 **Premium:**\n"
        text += "• Безлимит запросов\n"
        text += "• 50 картинок в день\n"
        text += "• Приоритетная обработка"
        
        await callback.message.edit_text(text, reply_markup=main_menu())
        await callback.answer()
    except Exception as e:
        logger.error(f"Help callback error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: types.CallbackQuery):
    try:
        text = "🤖 **Vertex AI**\n\n"
        text += "🧠 Искусственный интеллект в твоем Telegram!\n\n"
        text += "🎁 **Пробный период:**\n"
        text += "• 2 дня бесплатно\n"
        text += "• 5 картинок в день\n\n"
        text += "✅ 10 текстовых запросов/день\n"
        text += "💎 Premium: безлимит\n"
        text += "👥 Приведи друга → +5 запросов\n\n"
        text += "Просто напиши свой вопрос!"
        
        await callback.message.edit_text(text, reply_markup=main_menu())
        await callback.answer()
    except Exception as e:
        logger.error(f"Back to main error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
