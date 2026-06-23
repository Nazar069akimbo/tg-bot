from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import get_user, can_generate_image, add_image_request, get_user_plan
from keyboards import main_menu
import logging
import requests
import os
import time
import asyncio

router = Router()
logger = logging.getLogger(__name__)

BOTHUB_API_KEY = os.getenv('BOTHUB_API_KEY')

# Ключевые слова для определения запроса на картинку
IMAGE_KEYWORDS = [
    "нарисуй", "сгенерируй", "картинку", "изображение", "покажи", 
    "сделай", "draw", "image", "создай", "генерация", "рисунок",
    "картина", "иллюстрация", "арт", "фон", "обои", "пейзаж",
    "портрет", "нарисовать", "изобрази", "сгенерировать"
]

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
        f"📝 Примеры:\n"
        f"• кот в космосе\n"
        f"• горы и закат\n"
        f"• киберпанк город\n\n"
        f"📊 Твой план: {plan.upper()}\n"
        f"🎯 Осталось картинок: {remaining if not can_gen else '✅ доступно'}"
    )

@router.message(F.text)
async def generate_image(message: types.Message):
    if not message.text or message.text.startswith("/"):
        return
    
    # Проверяем, админ ли это в режиме поиска
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
    
    # Проверяем, хочет ли пользователь картинку
    is_image_request = any(kw in text for kw in IMAGE_KEYWORDS) or len(text.split()) < 5
    
    if not is_image_request:
        return
    
    # Проверяем лимиты
    can_gen, remaining = can_generate_image(message.from_user.id)
    if not can_gen:
        await message.answer(
            f"❌ Лимит картинок исчерпан!\n\n"
            f"🎯 Осталось: {remaining}\n"
            f"💎 Купи Premium для большего количества: /subscribe"
        )
        return
    
    # Генерируем картинку с прогрессом
    status_msg = await message.answer("🎨 Генерирую картинку... 0%")
    
    try:
        prompt = message.text
        
        # Имитация прогресса (для красоты)
        for percent in [10, 25, 45, 60, 75, 90]:
            await asyncio.sleep(0.3)
            try:
                await status_msg.edit_text(f"🎨 Генерирую картинку... {percent}%")
            except:
                pass
        
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
                await status_msg.edit_text("🎨 Генерирую картинку... 100% ✅")
                await asyncio.sleep(0.5)
                
                await message.answer_photo(
                    photo=image_url,
                    caption=f"🖼️ **Твоя картинка**\n📝 Запрос: {prompt[:100]}{'...' if len(prompt) > 100 else ''}"
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
    plan = get_user_plan(callback.from_user.id)
    can_gen, remaining = can_generate_image(callback.from_user.id)
    
    await callback.answer("🖼️ Напиши текст для картинки в чат!")
    await callback.message.edit_text(
        f"🖼️ **Генерация картинки**\n\n"
        f"Просто напиши в чат, что хочешь нарисовать.\n\n"
        f"📝 Примеры:\n"
        f"• кот в космосе\n"
        f"• горы и закат\n"
        f"• киберпанк город\n\n"
        f"📊 Твой план: {plan.upper()}\n"
        f"🎯 Осталось картинок: {remaining if not can_gen else '✅ доступло'}",
        reply_markup=main_menu()
    )
