from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import set_mode
from keyboards import main_menu

router = Router()

@router.message(Command("settings"))
async def settings_cmd(message: types.Message):
    await message.answer(
        "⚙️ **Настройки**\n\n"
        "Бот всегда работает в режиме ChatGPT.\n"
        "Просто задавайте любые вопросы!",
        reply_markup=main_menu()
    )

@router.callback_query(F.data == "settings")
async def settings_callback(callback: types.CallbackQuery):
    try:
        await callback.message.edit_text(
            "⚙️ **Настройки**\n\n"
            "Бот всегда работает в режиме ChatGPT.\n"
            "Просто задавайте любые вопросы!",
            reply_markup=main_menu()
        )
        await callback.answer()
    except Exception as e:
        await callback.answer()
