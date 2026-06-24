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
    
    # ===== ПРОВЕРКА ПРОБНОГО ПЕРИОДА =====
    trial_remaining = get_trial_remaining(user_id)
    can_gen, remaining = can_generate_image(user_id)
    
    # Если есть пробный период и остались картинки
    if trial_remaining > 0:
        can_gen = True
        remaining = trial_remaining
        logger.info(f"🎁 Пробный период: осталось {trial_remaining} картинок")
    else:
        # Проверяем, активен ли пробный период (показываем сообщение)
        if is_trial_active(user_id) and trial_remaining == 0:
            await message.answer(
                f"🎁 **Пробный период активен, но лимит исчерпан!**\n\n"
                f"📊 Сегодня использовано: 5/5 картинок\n"
                f"⏳ Завтра лимит обновится\n\n"
                f"💎 Купи Premium для безлимита: /subscribe"
            )
            return
    
    # Если нет пробного периода и нет Premium
    if not can_gen and not is_trial_active(user_id):
        await message.answer(
            f"❌ Лимит картинок исчерпан!\n\n"
            f"📊 Осталось: {remaining}\n"
            f"💎 Купи Premium: /subscribe"
        )
        return
    
    status_msg = await message.answer("🎨 Генерирую картинку...")
    
    try:
        prompt = message.text
        
        for p in [10, 25, 45, 60, 75, 90]:
            await asyncio.sleep(0.2)
            try:
                await status_msg.edit_text(f"🎨 Генерирую картинку... {p}%")
            except:
                pass
        
        url = "https://bothub.chat/api/v2/replicate/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {BOTHUB_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": IMAGE_MODEL,
            "input": {
                "prompt": prompt,
                "aspect_ratio": "1:1",
                "output_format": "webp"
            },
            "bothub": {
                "include_usage": True,
                "return_base64": False
            }
        }
        
        logger.info(f"🖼️ Модель: {IMAGE_MODEL}")
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
                        await status_msg.edit_text("🎨 Генерирую картинку... 100% ✅")
                        await asyncio.sleep(0.2)
                        
                        from aiogram.types import BufferedInputFile
                        image_file = BufferedInputFile(image_data, filename="image.webp")
                        
                        await message.answer_photo(
                            photo=image_file,
                            caption=f"🖼️ **Твоя картинка**\n📝 {prompt[:100]}{'...' if len(prompt) > 100 else ''}"
                        )
                        
                        # Списываем картинку
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
            await status_msg.edit_text(f"❌ Ошибка {response.status_code}. Попробуй позже.")
            
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
