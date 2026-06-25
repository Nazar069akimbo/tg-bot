from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import get_user, can_generate_image, add_image_request, get_user_plan
from keyboards import main_menu
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("image"))
async def image_cmd(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if not user:
        await message.answer("👋 Напишите /start для регистрации")
        return
    
    plan = get_user_plan(user_id)
    can_gen, remaining = can_generate_image(user_id)
    
    await message.answer(
        f"🖼️ **Генерация картинок**\n\n"
        f"Просто напиши текст, и я нарисую картинку!\n\n"
        f"📊 Твой план: {plan.upper()}\n"
        f"🎯 Осталось картинок: {remaining if not can_gen else '✅ доступно'}"
    )

@router.callback_query(F.data == "generate_image")
async def generate_image_callback(callback: types.CallbackQuery):
    plan = get_user_plan(callback.from_user.id)
    can_gen, remaining = can_generate_image(callback.from_user.id)
    
    await callback.answer("🖼️ Напиши текст для картинки в чат!")
    await callback.message.edit_text(
        f"🖼️ **Генерация картинки**\n\n"
        f"Просто напиши в чат, что хочешь нарисовать.\n\n"
        f"📊 Твой план: {plan.upper()}\n"
        f"🎯 Осталось картинок: {remaining if not can_gen else '✅ доступно'}",
        reply_markup=main_menu()
    )
