from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import get_user, can_generate_image, add_image_request, get_user_plan
from keyboards import main_menu
import logging
import requests
import os

router = Router()
logger = logging.getLogger(__name__)

BOTHUB_API_KEY = os.getenv('BOTHUB_API_KEY')

@router.message(Command("image"))
async def image_cmd(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if not user:
        await message.answer("👋 Напишите /start для регистрации")
        return
    
    await message.answer(
        "🖼️ **Генерация картинок**\n\n"
        "Просто напиши текст, и я нарисую картинку!\n\n"
        "📝 Примеры:\n"
        "• кот в космосе\n"
        "• горы и закат\n"
        "• киберпанк город\n\n"
        "💰 Цена: 1 запрос = 1 картинка\n\n"
        "📊 Твой план: " + get_user_plan(user_id)
    )

@router.message(F.text)
async def generate_image(message: types.Message):
    if not message.text or message.text.startswith("/"):
        return
    
    try:
        from handlers.admin_handler import user_pages
        state = user_pages.get(message.from_user.id, {})
        if state.get("state") in ["waiting_user_search", "waiting_admin_message"]:
            return
    except:
        pass
    
    user = get_user(message.from_user.id)
    if not user:
        return
    
    text = message.text.lower()
    keywords = ["нарисуй", "сгенерируй", "картинку", "изображение", "покажи", "сделай", "draw", "image"]
    is_image_request = any(kw in text for kw in keywords) or len(text.split()) < 5
    
    if not is_image_request:
        return
    
    can_generate, remaining = can_generate_image(message.from_user.id)
    if not can_generate:
        await message.answer(
            f"❌ Лимит картинок исчерпан!\n\n"
            f"📊 Осталось: {remaining}\n"
            f"💎 Купи Premium для большего количества!"
        )
        return
    
    status_msg = await message.answer("🎨 Генерирую картинку...")
    
    try:
        prompt = message.text
        
        url = "https://api.bothub.chat/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {BOTHUB_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "gpt-image",
            "prompt": prompt,
            "n": 1,
            "size": "512x512"
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            image_url = result.get('data', [{}])[0].get('url')
            
            if image_url:
                await message.answer_photo(
                    photo=image_url,
                    caption=f"🖼️ **Твоя картинка**\n📝 Запрос: {prompt[:50]}..."
                )
                add_image_request(message.from_user.id)
                await status_msg.delete()
            else:
                await status_msg.edit_text("❌ Не удалось сгенерировать картинку. Попробуй другой запрос.")
        else:
            await status_msg.edit_text("❌ Ошибка генерации. Попробуй позже.")
            
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        await status_msg.edit_text("❌ Ошибка. Попробуй позже.")

@router.callback_query(F.data == "generate_image")
async def generate_image_callback(callback: types.CallbackQuery):
    await callback.answer("🖼️ Напиши текст для картинки в чат!")
    await callback.message.edit_text(
        "🖼️ **Генерация картинки**\n\n"
        "Просто напиши в чат, что хочешь нарисовать.\n\n"
        "📝 Примеры:\n"
        "• кот в космосе\n"
        "• горы и закат\n"
        "• киберпанк город\n\n"
        "📊 Твой план: " + get_user_plan(callback.from_user.id),
        reply_markup=main_menu()
    )
