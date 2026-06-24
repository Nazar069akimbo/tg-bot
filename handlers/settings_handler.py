from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import get_user_mode, set_user_mode
from keyboards import main_menu

router = Router()

@router.message(Command("settings"))
async def settings_cmd(message: types.Message):
    mode = get_user_mode(message.from_user.id)
    mode_text = "🧠 Текст" if mode == "text" else "🖼️ Картинка"
    
    await message.answer(
        f"⚙️ **Настройки**\n\n"
        f"📊 Текущий режим: {mode_text}\n\n"
        f"Выбери режим в главном меню: 🧠 Текст или 🖼️ Картинка"
    )

@router.callback_query(F.data == "mode_text")
async def mode_text(callback: types.CallbackQuery):
    set_user_mode(callback.from_user.id, "text")
    await callback.answer("✅ Режим: 🧠 Текст", show_alert=True)
    await callback.message.edit_text(
        "🧠 **Режим Текст**\n\n"
        "Теперь я буду отвечать на твои вопросы текстом.\n\n"
        "Просто напиши что-нибудь!",
        reply_markup=main_menu()
    )

@router.callback_query(F.data == "mode_image")
async def mode_image(callback: types.CallbackQuery):
    set_user_mode(callback.from_user.id, "image")
    await callback.answer("✅ Режим: 🖼️ Картинка", show_alert=True)
    await callback.message.edit_text(
        "🖼️ **Режим Картинка**\n\n"
        "Теперь я буду генерировать картинки по твоим описаниям.\n\n"
        "Просто напиши, что хочешь увидеть!",
        reply_markup=main_menu()
    )
