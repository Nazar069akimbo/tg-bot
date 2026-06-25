from aiogram import Router, types, F
from aiogram.filters import Command
from keyboards import main_menu

router = Router()
user_modes = {}

@router.message(Command("settings"))
async def settings_cmd(message: types.Message):
    mode = user_modes.get(message.from_user.id, "text")
    mode_text = "🧠 Текст" if mode == "text" else "🖼️ Картинка"
    
    await message.answer(
        f"⚙️ **Настройки**\n\n"
        f"📊 Текущий режим: {mode_text}\n\n"
        f"Выбери режим в главном меню: 🧠 Текст или 🖼️ Картинка"
    )

@router.callback_query(F.data == "mode_text")
async def mode_text(callback: types.CallbackQuery):
    user_modes[callback.from_user.id] = "text"
    await callback.answer("✅ Режим: 🧠 Текст", show_alert=True)
    await callback.message.edit_text(
        "🧠 **Режим Текст**\n\nТеперь я буду отвечать на твои вопросы текстом.",
        reply_markup=main_menu()
    )

@router.callback_query(F.data == "mode_image")
async def mode_image(callback: types.CallbackQuery):
    user_modes[callback.from_user.id] = "image"
    await callback.answer("✅ Режим: 🖼️ Картинка", show_alert=True)
    await callback.message.edit_text(
        "🖼️ **Режим Картинка**\n\nТеперь я буду генерировать картинки по твоим описаниям.",
        reply_markup=main_menu()
    )
