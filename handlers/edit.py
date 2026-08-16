from aiogram import Router, types, F
from database.db import *
from . import helpers
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data.startswith("edit_"))
async def edit_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    image_id = int(callback.data.replace("edit_", ""))
    image = get_image_by_id(image_id)
    if not image:
        await helpers.safe_answer(callback, "❌ Картинка не найдена", show_alert=True)
        return
    helpers.user_pages[user_id] = {"state": "waiting_edit", "image_id": image_id}
    await callback.message.answer("✏️ Напиши, что изменить:", reply_markup=helpers.edit_in_progress_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "cancel_edit")
async def cancel_edit_cb(callback: types.CallbackQuery):
    helpers.user_pages.pop(callback.from_user.id, None)
    await callback.message.edit_text("✅ Отменено", reply_markup=helpers.main_menu())
    await helpers.safe_answer(callback)
