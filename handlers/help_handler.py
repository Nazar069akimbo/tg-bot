from aiogram import Router, types, F
from aiogram.filters import Command

router = Router()

@router.message(Command("help"))
async def help_cmd(message: types.Message):
    text = "❓ **Vertex AI — Помощь**\n\n"
    text += "🤖 **Что я умею:**\n"
    text += "• Отвечаю на любые вопросы\n"
    text += "• Решаю задачи по математике\n"
    text += "• Помогаю с учебой\n\n"
    text += "📋 **Команды:**\n"
    text += "/start — Запустить бота\n"
    text += "/stats — Статистика\n"
    text += "/profile — Профиль\n"
    text += "/settings — Настройки\n"
    text += "/subscribe — Premium\n"
    text += "/referral — Рефералы\n"
    text += "/leaderboard — Рейтинг\n"
    text += "/admin — Админ-панель\n\n"
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
        text += "• Решаю задачи по математике\n"
        text += "• Помогаю с учебой\n\n"
        text += "📋 **Команды:**\n"
        text += "/start — Запустить бота\n"
        text += "/stats — Статистика\n"
        text += "/profile — Профиль\n"
        text += "/settings — Настройки\n"
        text += "/subscribe — Premium\n"
        text += "/referral — Рефералы\n"
        text += "/leaderboard — Рейтинг\n"
        text += "/admin — Админ-панель\n\n"
        text += "💎 **Premium:**\n"
        text += "• Безлимит запросов\n"
        text += "• 3000 символов на запрос\n"
        text += "• Приоритетная обработка"
        await callback.message.edit_text(text)
        await callback.answer()
    except Exception as e:
        await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: types.CallbackQuery):
    from keyboards import main_menu
    await callback.message.edit_text(
        "🤖 **Vertex AI**\n\n"
        "🧠 Искусственный интеллект в твоем Telegram!\n\n"
        "✅ 10 запросов в день бесплатно\n"
        "💎 Premium: безлимит\n"
        "👥 Приведи друга → +5 запросов\n\n"
        "Выбери режим работы:",
        reply_markup=main_menu()
    )
    await callback.answer()
