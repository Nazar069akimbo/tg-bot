from aiogram import Router, types, F
from database.db import get_user, can_request, add_request, is_premium, can_generate_image, add_image_request
from database.db import is_trial_active, get_trial_remaining, use_trial_image
from ai import solve_problem
from keyboards import main_menu
import logging
import requests
import os

router = Router()
logger = logging.getLogger(__name__)

BOTHUB_API_KEY = os.getenv('OPENAI_API_KEY')
from handlers.settings_handler import user_modes

IMAGE_MODEL = "flux-schnell"
PROMPT_MODEL = "gpt-4.1-nano"

@router.message(F.text)
async def handle_message(message: types.Message):
    # Пропускаем команды
    if message.text.startswith('/'):
        return
    
    # Пропускаем если пользователь в режиме админки
    try:
        from handlers.admin_handler import user_pages as admin_pages
        state = admin_pages.get(message.from_user.id, {})
        if state.get("state") in ["waiting_user_search", "waiting_admin_message", "waiting_broadcast", "confirm_broadcast"]:
            return
    except:
        pass
    
    # Пропускаем если пользователь в режиме контакта
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
        await message.answer(result_text)


async def generate_image(message: types.Message):
    user_id = message.from_user.id
    
    trial_remaining = get_trial_remaining(user_id)
    can_gen, remaining = can_generate_image(user_id)
    
    if trial_remaining > 0:
        can_gen = True
    elif is_trial_active(user_id) and trial_remaining == 0:
        await message.answer("🎁 Пробный лимит исчерпан! Купи Premium: /subscribe")
        return
    
    if not can_gen and not is_trial_active(user_id):
        await message.answer(f"❌ Лимит картинок исчерпан! Купи Premium: /subscribe")
        return
    
    status_msg = await message.answer("🎨 Генерирую...")
    
    try:
        enhanced_prompt = message.text
        
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
                    from aiogram.types import BufferedInputFile
                    image_file = BufferedInputFile(img_response.content, filename="image.webp")
                    await message.answer_photo(photo=image_file, caption=f"🖼️ {message.text[:100]}")
                    
                    if trial_remaining > 0:
                        use_trial_image(user_id)
                    else:
                        add_image_request(user_id)
                    
                    await status_msg.delete()
                    return
            
            await status_msg.edit_text("❌ Не удалось создать картинку")
        else:
            await status_msg.edit_text(f"❌ Ошибка генерации")
    except Exception as e:
        logger.error(f"Image error: {e}")
        await status_msg.edit_text("❌ Ошибка. Попробуй позже.")
