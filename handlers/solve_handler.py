from aiogram import Router, types, F
from database.db import get_user, can_request, add_request, is_premium, can_generate_image, add_image_request
from ai import solve_problem
from keyboards import main_menu
import logging
import asyncio
import requests
import os
import json
import re

router = Router()
logger = logging.getLogger(__name__)

BOTHUB_API_KEY = os.getenv('BOTHUB_API_KEY')

from handlers.settings_handler import user_modes

# ===== МОДЕЛИ, КОТОРЫЕ МОГУТ ГЕНЕРИРОВАТЬ КАРТИНКИ (через чат) =====
IMAGE_MODELS = [
    "gpt-image-1-mini",
    "gpt-image-1.5",
    "gpt-image-2",
    "gpt-image-1",
    "mai-image-2.5",
    "seedream-4.5",
    "grok-imagine-image-quality"
]

@router.message(F.text)
async def handle_message(message: types.Message):
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
        await message.answer("👋 Напиши /start", reply_markup=main_menu())
        return
    
    mode = user_modes.get(message.from_user.id, "text")
    
    if mode == "image":
        await generate_image(message)
    else:
        await generate_text(message)

async def generate_text(message: types.Message):
    ok, remaining = can_request(message.from_user.id)
    if not ok:
        await message.answer("🔒 Лимит исчерпан! Купи Premium: /subscribe")
        return
    
    premium = is_premium(message.from_user.id)
    status_msg = await message.answer("🤔 Думаю...")
    
    answer = solve_problem(message.text, "chat", premium)
    add_request(message.from_user.id)
    
    remaining_after = remaining - 1 if not premium else "∞"
    result_text = f"🧠 {answer}\n\n"
    if not premium:
        result_text += f"🎯 Осталось запросов: {remaining_after}"
    else:
        result_text += "💎 Premium — безлимит"
    
    await status_msg.edit_text(result_text)

async def generate_image(message: types.Message):
    user_id = message.from_user.id
    
    can_gen, remaining = can_generate_image(user_id)
    if not can_gen:
        await message.answer(
            f"❌ Лимит картинок исчерпан!\n\n"
            f"Осталось: {remaining}\n"
            f"💎 Купи Premium: /subscribe"
        )
        return
    
    status_msg = await message.answer("🎨 Генерирую картинку... 0%")
    
    try:
        prompt = message.text
        
        for p in [10, 25, 45, 60, 75, 90]:
            await asyncio.sleep(0.3)
            try:
                await status_msg.edit_text(f"🎨 Генерирую картинку... {p}%")
            except:
                pass
        
        url = "https://openai.bothub.chat/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {BOTHUB_API_KEY}",
            "Content-Type": "application/json"
        }
        
        image_url = None
        last_error = None
        
        # Перебираем модели
        for model in IMAGE_MODELS:
            try:
                data = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "Ты — генератор изображений. Создай картинку по описанию. Верни только прямую ссылку на картинку (URL). Никакого другого текста."},
                        {"role": "user", "content": f"Создай изображение: {prompt}"}
                    ],
                    "max_tokens": 500,
                    "temperature": 0.8
                }
                
                logger.info(f"🖼️ Пробую модель: {model}")
                response = requests.post(url, headers=headers, json=data, timeout=60)
                
                if response.status_code == 200:
                    result = response.json()
                    content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
                    
                    # Ищем URL в ответе
                    urls = re.findall(r'https?://[^\s<>"\']+\.(?:jpg|jpeg|png|gif|webp)', content)
                    if urls:
                        image_url = urls[0]
                        logger.info(f"✅ Найдена картинка через {model}")
                        break
                    else:
                        logger.warning(f"⚠️ Нет URL в ответе {model}")
                else:
                    logger.warning(f"⚠️ Модель {model} вернула {response.status_code}")
                    last_error = response.status_code
            except Exception as e:
                logger.warning(f"⚠️ Ошибка с моделью {model}: {e}")
                continue
        
        if image_url:
            await status_msg.edit_text("🎨 Генерирую картинку... 100% ✅")
            await asyncio.sleep(0.3)
            
            await message.answer_photo(
                photo=image_url,
                caption=f"🖼️ **Твоя картинка**\n📝 {prompt[:100]}{'...' if len(prompt) > 100 else ''}"
            )
            add_image_request(user_id)
            await status_msg.delete()
        else:
            await status_msg.edit_text(
                f"❌ Не удалось сгенерировать картинку.\n\n"
                f"Попробуй:\n"
                f"• написать более детальное описание\n"
                f"• использовать английский язык\n"
                f"• попробовать позже"
            )
            
    except Exception as e:
        logger.error(f"❌ Image error: {e}")
        await status_msg.edit_text("❌ Ошибка. Попробуй позже.")

@router.callback_query(F.data == "ask_question")
async def ask_question(callback: types.CallbackQuery):
    await callback.answer("Напиши свой вопрос в чат!", show_alert=True)
    await callback.message.edit_text(
        "🧠 **Задать вопрос**\n\n"
        "Просто напиши мне свой вопрос в чат!",
        reply_markup=main_menu()
    )
