from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import get_user_mode, set_user_mode
from keyboards import main_menu, mode_selector

router = Router()

@router.message(Command("settings"))
async def settings_cmd(message: types.Message):
    mode = get_user_mode(message.from_user.id)
    mode_text = "🧠 Текст" if mode == "text" else "🖼️ Картинка"
    
    await message.answer(
        f"⚙️ **Настройки**\n\n"
        f"📊 Текущий режим: {mode_text}\n\n"
        f"Выберите режим работы:",
        reply_markup=mode_selector()
    )

@router.callback_query(F.data == "settings")
async def settings_callback(callback: types.CallbackQuery):
    try:
        mode = get_user_mode(callback.from_user.id)
        mode_text = "🧠 Текст" if mode == "text" else "🖼️ Картинка"
        
        await callback.message.edit_text(
            f"⚙️ **Настройки**\n\n"
            f"📊 Текущий режим: {mode_text}\n\n"
            f"Выберите режим работы:",
            reply_markup=mode_selector()
        )
        await callback.answer()
    except Exception as e:
        await callback.answer()

@router.callback_query(F.data == "mode_text")
async def mode_text(callback: types.CallbackQuery):
    set_user_mode(callback.from_user.id, "text")
    await callback.answer("✅ Режим: 🧠 Текст", show_alert=True)
    await settings_callback(callback)

@router.callback_query(F.data == "mode_image")
async def mode_image(callback: types.CallbackQuery):
    set_user_mode(callback.from_user.id, "image")
    await callback.answer("✅ Режим: 🖼️ Картинка", show_alert=True)
    await settings_callback(callback)
