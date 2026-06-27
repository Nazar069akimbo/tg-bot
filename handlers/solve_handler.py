from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import (
    get_user, can_request, add_request, is_premium, 
    can_generate_image, add_image_request, get_image_stats,
    is_trial_active, get_trial_remaining, use_trial_image,
    reset_image_count_if_needed
)
from ai import solve_problem
from keyboards import main_menu
import logging
import asyncio
import requests
import os

router = Router()
logger = logging.getLogger(__name__)

API_KEY = os.getenv('OPENAI_API_KEY')
if not API_KEY:
    logger.error("❌ OPENAI_API_KEY не найден!")

from handlers.settings_handler import user_modes

IMAGE_MODEL = "flux-schnell"
PROMPT_MODEL = "gpt-4.1-nano"

@router.message(F.text)
async def handle_message(message: types.Message):
    if not message.text or message.text.startswith("/"):
        return
    
    from handlers.admin_handler import user_pages as admin_pages
    admin_state = admin_pages.get(message.from_user.id, {})
    if admin_state.get("state") in ["waiting_user_search", "waiting_admin_message", "waiting_broadcast", "confirm_broadcast"]:
        return
    
    from handlers.contact_handler import user_pages as contact_pages
    contact_state = contact_pages.get(message.from_user.id, {})
    if contact_state.get("state") == "waiting_contact":
        return
    
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("👋 Напиши /start", reply_markup=main_menu())
        return
    
    mode = user_modes.get(message.from_user.id, "text")
    logger.info(f"Режим пользователя {message.from_user.id}: {mode}")
    
    if mode == "image":
        await generate_image(message)
    else:
        await generate_text(message)

async def generate_text(message: types.Message):
    ok, remaining = can_request(message.from_user.id)
    if not ok:
        await message.answer(
            f"🔒 **Лимит текстовых запросов исчерпан!**\n\n"
            f"📊 Осталось: 0\n"
            f"💎 Купи Premium для безлимита: /subscribe"
        )
        return
    
    premium = is_premium(message.from_user.id)
    status_msg = await message.answer("🤔 Думаю...")
    
    try:
        answer = solve_problem(message.text, "chat", premium)
        add_request(message.from_user.id)
    except Exception as e:
        logger.error(f"Ошибка при генерации текста: {e}")
        await status_msg.edit_text("❌ Ошибка при обработке запроса. Попробуйте позже.")
        return
    
    remaining_after = remaining - 1 if not premium else "∞"
    result_text = f"🧠 {answer}\n\n"
    if not premium:
        result_text += f"🎯 Осталось запросов: {remaining_after}"
    else:
        result_text += "💎 Premium — безлимит"
    
    await status_msg.edit_text(result_text)

async def generate_image(message: types.Message):
    user_id = message.from_user.id
    
    # Сбрасываем счётчик если прошёл день
    reset_image_count_if_needed(user_id)
    
    # Проверяем лимит
    can_gen, remaining = can_generate_image(user_id)
    used, limit, is_prem = get_image_stats(user_id)
    
    trial_remaining = get_trial_remaining(user_id)
    if trial_remaining > 0 and not is_prem:
        can_gen = True
        remaining = trial_remaining
        limit = 5
        used = 5 - trial_remaining
        logger.info(f"🎁 Пробный период: осталось {trial_remaining} картинок")
    
    if not can_gen:
        if is_prem:
            await message.answer(
                f"❌ **Лимит картинок исчерпан!**\n\n"
                f"📊 Использовано: {used}/{limit}\n"
                f"⏳ Подождите до завтра"
            )
        else:
            await message.answer(
                f"❌ **Лимит картинок исчерпан!**\n\n"
                f"📊 Использовано: {used}/{limit}\n"
                f"⏳ Лимит обновится завтра\n\n"
                f"💎 Купи Premium для увеличения лимита: /subscribe"
            )
        return
    
    if is_trial_active(user_id) and trial_remaining == 0 and not is_prem:
        await message.answer(
            f"🎁 **Пробный период закончился!**\n\n"
            f"📊 Вы использовали все 5 картинок\n"
            f"💎 Купи Premium для безлимита: /subscribe"
        )
        return
    
    status_msg = await message.answer("🎨 Думаю над твоим запросом...")
    
    try:
        user_prompt = message.text
        
        await status_msg.edit_text("🔍 Создаю детальное описание...")
        
        prompt_url = "https://openai.bothub.chat/v1/chat/completions"
        prompt_headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        
        prompt_data = {
            "model": PROMPT_MODEL,
            "messages": [
                {"role": "system", "content": "You are a professional prompt engineer. Convert the user's request into a detailed English prompt for Flux/Stable Diffusion. Rules: 1. ALWAYS respond ONLY in English 2. Prompt should be 30-60 words 3. Add details: style, lighting, mood, colors 4. Use quality keywords: photorealistic, 8k, highly detailed. Only the prompt, no explanations!"},
                {"role": "user", "content": f"Create a prompt for: {user_prompt}"}
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
            logger.info(f"📝 Промпт: {enhanced_prompt[:100]}...")
        else:
            enhanced_prompt = user_prompt
            logger.warning(f"⚠️ Не удалось создать промпт, используем исходный")
        
        await status_msg.edit_text("🎨 Генерирую картинку...")
        
        url = "https://bothub.chat/api/v2/replicate/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {API_KEY}",
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
                        await status_msg.edit_text("🎨 Готово! ✅")
                        await asyncio.sleep(0.2)
                        
                        from aiogram.types import BufferedInputFile
                        image_file = BufferedInputFile(image_data, filename="image.webp")
                        
                        if trial_remaining > 0 and not is_premium(user_id):
                            use_trial_image(user_id)
                        else:
                            add_image_request(user_id)
                        
                        new_used, new_limit, new_prem = get_image_stats(user_id)
                        caption = f"🖼️ **Твоя картинка**\n\n📝 {user_prompt[:100]}{'...' if len(user_prompt) > 100 else ''}\n\n📊 Осталось картинок: {new_limit - new_used}\n💎 Статус: {'💎 Premium' if new_prem else '🔴 Бесплатный'}"
                        
                        await message.answer_photo(photo=image_file, caption=caption)
                        await status_msg.delete()
                        return
        
        await status_msg.edit_text("❌ Не удалось получить картинку. Попробуй другой запрос.")
    except Exception as e:
        logger.error(f"❌ Image error: {e}")
        await status_msg.edit_text("❌ Ошибка. Попробуй позже.")

@router.callback_query(F.data == "ask_question")
async def ask_question(callback: types.CallbackQuery):
    await callback.answer("Напиши свой вопрос в чат!", show_alert=True)
    await callback.message.edit_text(
        "🧠 **Задать вопрос**\n\nПросто напиши мне свой вопрос в чат!",
        reply_markup=main_menu()
    )
