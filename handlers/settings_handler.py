from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import set_mode
from keyboards import main_menu

router = Router()

@router.message(Command("settings"))
async def settings_cmd(message: types.Message):
    await message.answer(
        "⚙️ **Настройки**\n\n"
        "Выбери режим работы:",
        reply_markup=main_menu()
    )

@router.callback_query(F.data == "settings")
async def settings_callback(callback: types.CallbackQuery):
    try:
        await callback.message.edit_text(
            "⚙️ **Настройки**\n\n"
            "Выбери режим работы:",
            reply_markup=main_menu()
        )
        await callback.answer()
    except Exception as e:
        await callback.answer()

@router.callback_query(F.data == "mode_gdz")
async def mode_gdz(callback: types.CallbackQuery):
    try:
        set_mode(callback.from_user.id, "gdz")
        await callback.message.edit_text("✅ Режим: 📚 ГДЗ")
        await callback.answer()
    except Exception as e:
        await callback.answer()

@router.callback_query(F.data == "mode_chat")
async def mode_chat(callback: types.CallbackQuery):
    try:
        set_mode(callback.from_user.id, "chat")
        await callback.message.edit_text("✅ Режим: 💬 Общение")
        await callback.answer()
    except Exception as e:
        await callback.answer()
