from aiogram import Router, types, F
from aiogram.filters import Command

router = Router()

@router.message(Command("help"))
async def help_cmd(message: types.Message):
    text = "❓ **Команды:**\n\n"
    text += "/start — Запустить бота\n"
    text += "/stats — Статистика\n"
    text += "/profile — Профиль\n"
    text += "/settings — Настройки\n"
    text += "/subscribe — Premium\n"
    text += "/referral — Рефералы\n"
    text += "/leaderboard — Рейтинг\n"
    text += "/admin — Админ-панель"
    await message.answer(text)

@router.callback_query(F.data == "help")
async def help_callback(callback: types.CallbackQuery):
    try:
        text = "❓ **Команды:**\n\n"
        text += "/start — Запустить бота\n"
        text += "/stats — Статистика\n"
        text += "/profile — Профиль\n"
        text += "/settings — Настройки\n"
        text += "/subscribe — Premium\n"
        text += "/referral — Рефералы\n"
        text += "/leaderboard — Рейтинг\n"
        text += "/admin — Админ-панель"
        await callback.message.edit_text(text)
        await callback.answer()
    except Exception as e:
        await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: types.CallbackQuery):
    from keyboards import main_menu
    await callback.message.edit_text(
        "🚀 **Флагман Решебник**\n\n"
        "✅ 10 задач в день бесплатно\n"
        "💎 Premium: безлимит\n"
        "👥 Приведи друга → +5 задач\n\n"
        "Выбери режим:",
        reply_markup=main_menu()
    )
    await callback.answer()
