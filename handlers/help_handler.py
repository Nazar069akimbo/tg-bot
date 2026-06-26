from aiogram import Router, types, F
from aiogram.filters import Command

router = Router()

@router.message(Command("help"))
async def help_cmd(message: types.Message):
    text = "❓ **Vertex AI — Помощь**\n\n"
    text += "🤖 **Что я умею:**\n"
    text += "• Отвечаю на любые вопросы\n"
    text += "• Помогаю с учебой\n"
    text += "• Решаю задачи\n\n"
    text += "📋 **Команды:**\n"
    text += "/start — Главное меню\n"
    text += "/profile — Профиль\n"
    text += "/stats — Статистика\n"
    text += "/subscribe — Premium\n"
    text += "/referral — Рефералы\n\n"
    text += "💎 **Premium:**\n"
    text += "• Безлимит запросов\n"
    text += "• 3000 символов на запрос\n"
    text += "• Приоритетная обработка"
    await message.answer(text)

@router.callback_query(F.data == "help")
async def help_callback(callback: types.CallbackQuery):
    try:
        text = "❓ **Vertex AI — Помощь**\n\n"
        text += "🤖 **Что я умею:**\n"
        text += "• Отвечаю на любые вопросы\n"
        text += "• Помогаю с учебой\n"
        text += "• Решаю задачи\n\n"
        text += "📋 **Команды:**\n"
        text += "/start — Главное меню\n"
        text += "/profile — Профиль\n"
        text += "/stats — Статистика\n"
        text += "/subscribe — Premium\n"
        text += "/referral — Рефералы\n\n"
        text += "💎 **Premium:**\n"
        text += "• Безлимит запросов\n"
        text += "• 3000 символов на запрос\n"
        text += "• Приоритетная обработка"
        await callback.message.edit_text(text)
        await callback.answer()
    except Exception as e:
        await callback.answer()
