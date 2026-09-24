from aiogram import Router, types, F
from database.db import *
from . import helpers
from .image import generate_image
import logging

router = Router()
logger = logging.getLogger(__name__)

async def handle_edit_message(message: types.Message):
    """Обработка текста при правке картинки (состояние waiting_edit)"""
    user_id = message.from_user.id
    state = helpers.user_pages.get(user_id, {})
    image_id = state.get("image_id")

    if not image_id:
        await message.answer("❌ Нет картинки для правки", reply_markup=helpers.main_menu())
        helpers.user_pages.pop(user_id, None)
        return

    image = get_image_by_id(image_id)
    if not image:
        await message.answer("❌ Картинка не найдена", reply_markup=helpers.main_menu())
        helpers.user_pages.pop(user_id, None)
        return

    edit_text = message.text.strip()
    logger.info(f"✏️ [{user_id}] Правка картинки {image_id}: {edit_text}")

    # Берём оригинальный промпт из БД
    full_prompt = f"{image.get('prompt', '')}, {edit_text}"

    helpers.user_pages.pop(user_id, None)
    await generate_image(message, full_prompt)

@router.callback_query(F.data.startswith("edit_"))
async def edit_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data

    # Проверяем, что это edit_ с числом
    if not data.startswith("edit_"):
        await callback.answer()
        return

    try:
        image_id_str = data.replace("edit_", "")
        if not image_id_str.isdigit():
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
