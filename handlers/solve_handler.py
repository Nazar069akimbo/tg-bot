from aiogram import Router, types, F
from database.db import get_user, can_request, add_request, is_premium, can_generate_image, add_image_request
from database.db import is_trial_active, get_trial_remaining, use_trial_image
from ai import solve_problem
from keyboards import main_menu
import logging
import asyncio
import requests
import os
import io

router = Router()
logger = logging.getLogger(__name__)

BOTHUB_API_KEY = os.getenv('OPENAI_API_KEY')

from handlers.settings_handler import user_modes

IMAGE_MODEL = "flux-schnell"
PROMPT_MODEL = "gpt-4.1-nano"

# Фильтр для текстовых сообщений (не команд)
@router.message(F.text, lambda msg: not msg.text.startswith('/'))
async def handle_message(message: types.Message):
    if not message.text:
        return
    
    # Проверяем, не находится ли пользователь в режиме админки
    try:
        from handlers.admin_handler import user_pages as admin_pages
        state = admin_pages.get(message.from_user.id, {})
        if state.get("state") in ["waiting_user_search", "waiting_admin_message", "waiting_broadcast", "confirm_broadcast"]:
            return
    except:
        pass
    
    # Проверяем, не находится ли пользователь в режиме контакта
    try:
        from handlers.contact_handler import user_pages as contact_pages
        state = contact_pages.get(message.from_user.id, {})
        if state.get("state") == "waiting_contact":
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
    
    try:
        await status_msg.edit_text(result_text)
    except:
        await status_msg.delete()
        await message.answer(result_text)


async def generate_image(message: types.Message):
    user_id = message.from_user.id
    
    trial_remaining = get_trial_remaining(user_id)
    can_gen, remaining = can_generate_image(user_id)
    
    if trial_remaining > 0:
        can_gen = True
        remaining = trial_remaining
    else:
        if is_trial_active(user_id) and trial_remaining == 0:
            await message.answer(
                f"🎁 **Пробный период активен, но лимит исчерпан!**\n\n"
                f"📊 Сегодня использовано: 5/5 картинок\n"
                f"⏳ Завтра лимит обновится\n\n"
                f"💎 Купи Premium для безлимита: /subscribe"
            )
            return
    
    if not can_gen and not is_trial_active(user_id):
        await message.answer(
            f"❌ Лимит картинок исчерпан!\n\n"
            f"📊 Осталось: {remaining}\n"
            f"💎 Купи Premium: /subscribe"
        )
        return
    
    status_msg = await message.answer("🎨 Генерирую картинку...")
    
    try:
        user_prompt = message.text
        
        # Создаем улучшенный промпт
        prompt_url = "https://openai.bothub.chat/v1/chat/completions"
        prompt_headers = {
            "Authorization": f"Bearer {BOTHUB_API_KEY}",
            "Content-Type": "application/json"
        }
        
        prompt_data = {
            "model": PROMPT_MODEL,
            "messages": [
                {"role": "system", "content": """Ты — профессиональный промпт-инженер для генерации изображений. 
                Твоя задача — превратить короткий запрос пользователя в детальный английский промпт для нейросети.
                
                Правила:
                1. Всегда отвечай ТОЛЬКО на английском языке
                2. Промпт должен быть от 30 до 60 слов
                3. Добавляй детали: стиль, освещение, настроение, цвета, композицию
                4. Используй ключевые слова для качества: photorealistic, 8k, highly detailed, masterpiece, sharp focus
                
                Только промпт, без пояснений!"""},
                {"role": "user", "content": f"Создай промпт для: {user_prompt}"}
            ],
            "max_tokens": 200,
            "temperature": 0.7
        }
        
        prompt_response = requests.post(prompt_url, headers=prompt_headers, json=prompt_data, timeout=30)
        
        if prompt_response.status_code == 200:
            prompt_result = prompt_response.json()
            enhanced_prompt = prompt_result.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
            if enhanced_prompt.startswith('"') and enhanced_prompt.endswith('"'):
                enhanced_prompt = enhanced_prompt[1:-1]
            logger.info(f"📝 Сгенерирован промпт: {enhanced_prompt[:100]}...")
        else:
            enhanced_prompt = user_prompt
        
        await status_msg.edit_text("🎨 Генерирую картинку...")
        
        url = "https://bothub.chat/api/v2/replicate/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {BOTHUB_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": IMAGE_MODEL,
            "input": {
                "prompt": enhanced_prompt,
                "aspect_ratio": "1:1",
                "output_format": "webp"
            },
            "bothub": {
                "include_usage": True,
                "return_base64": False
            }
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            image_url = result.get('url')
            if isinstance(image_url, list):
                image_url = image_url[0]
            
            if image_url:
                img_response = requests.get(image_url, timeout=30)
                if img_response.status_code == 200:
                    image_data = img_response.content
                    
                    if len(image_data) > 1000:
                        from aiogram.types import BufferedInputFile
                        image_file = BufferedInputFile(image_data, filename="image.webp")
                        
                        await message.answer_photo(
                            photo=image_file,
                            caption=f"🖼️ **Твоя картинка**\n📝 {user_prompt[:100]}{'...' if len(user_prompt) > 100 else ''}"
                        )
                        
                        if trial_remaining > 0:
                            use_trial_image(user_id)
                            logger.info(f"🎁 Использована пробная картинка, осталось: {trial_remaining - 1}")
                        else:
                            add_image_request(user_id)
                        
                        await status_msg.delete()
                        return
            
            await status_msg.edit_text("❌ Не удалось получить картинку. Попробуй другой запрос.")
        else:
            logger.error(f"❌ Ошибка: {response.status_code}")
            await status_msg.edit_text(f"❌ Ошибка генерации. Попробуй позже.")
            
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
