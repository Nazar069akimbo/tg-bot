from aiogram import Router, types, F
from database.db import *
from . import helpers
import logging, re

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data.startswith("edit_"))
async def edit_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    # Проверяем, что это именно edit_ с числом
    data = callback.data
    if not data.startswith("edit_"):
        await callback.answer("❌ Неверный формат", show_alert=True)
        return
    
    # Извлекаем ID (только если это edit_ЦИФРА)
    try:
        image_id_str = data.replace("edit_", "")
        if not image_id_str.isdigit():
            # Если это не число — игнорируем (это не наш колбэк)
            await callback.answer()
            return
        image_id = int(image_id_str)
    except ValueError:
        await callback.answer()
        return
    
    image = get_image_by_id(image_id)
    if not image:
        await helpers.safe_answer(callback, "❌ Картинка не найдена", show_alert=True)
        return
    
    helpers.user_pages[user_id] = {"state": "waiting_edit", "image_id": image_id}
    
    await callback.message.answer(
        "✏️ **Что изменить?**\n\n"
        "Напиши, что хочешь поменять:\n"
        "• *сделай кота чёрным*\n"
        "• *добавь шляпу*\n"
        "• *убери фон*\n\n"
        "⏹ /cancel",
        reply_markup=helpers.edit_in_progress_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "cancel_edit")
async def cancel_edit_cb(callback: types.CallbackQuery):
    helpers.user_pages.pop(callback.from_user.id, None)
    await callback.message.edit_text("✅ Отменено", reply_markup=helpers.main_menu())
    await helpers.safe_answer(callback)
