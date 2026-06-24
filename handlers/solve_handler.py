from aiogram import Router, types, F
from database.db import get_user, can_request, add_request, is_premium, can_generate_image, add_image_request
from ai import solve_problem
from keyboards import main_menu
import logging
import asyncio
import requests
import os
import io
import time

router = Router()
logger = logging.getLogger(__name__)

from handlers.settings_handler import user_modes

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
    
    status_msg = await message.answer("🎨 Генерирую картинку...")
    
    try:
        prompt = message.text
        
        for p in [10, 25, 45, 60, 75, 90]:
            await asyncio.sleep(0.2)
            try:
                await status_msg.edit_text(f"🎨 Генерирую картинку... {p}%")
            except:
                pass
        
        # ===== LEXICA API (БЕСПЛАТНО, БЕЗ КЛЮЧА) =====
        # Лучше понимает запросы
        url = "https://lexica.qvantum.xyz/api/generate"
        payload = {
            "prompt": prompt,
            "width": 512,
            "height": 512,
            "steps": 20,
            "cfg": 7,
            "sampler": "euler"
        }
        
        logger.info(f"🖼️ Запрос: {prompt[:50]}...")
        response = requests.post(url, json=payload, timeout=60)
        
        if response.status_code == 200:
            data = response.json()
            image_base64 = data.get('image')
            
            if image_base64:
                import base64
                image_data = base64.b64decode(image_base64)
                
                await status_msg.edit_text("🎨 Генерирую картинку... 100% ✅")
                
                from aiogram.types import BufferedInputFile
                image_file = BufferedInputFile(image_data, filename="image.png")
                
                await message.answer_photo(
                    photo=image_file,
                    caption=f"🖼️ **Твоя картинка**\n📝 {prompt[:100]}{'...' if len(prompt) > 100 else ''}"
                )
                add_image_request(user_id)
                await status_msg.delete()
            else:
                await status_msg.edit_text("❌ Не удалось сгенерировать картинку. Попробуй другой запрос.")
        else:
            logger.error(f"❌ Ошибка: {response.status_code}")
            await status_msg.edit_text(f"❌ Ошибка {response.status_code}. Попробуй позже.")
            
    except requests.exceptions.Timeout:
        await status_msg.edit_text("❌ Превышено время ожидания. Попробуй позже.")
    except Exception as e:
        logger.error(f"Image error: {e}")
        await status_msg.edit_text("❌ Ошибка. Попробуй позже.")

@router.callback_query(F.data == "ask_question")
async def ask_question(callback: types.CallbackQuery):
    await callback.answer("Напиши свой вопрос в чат!", show_alert=True)
    await callback.message.edit_text(
        "🧠 **Задать вопрос**\n\n"
        "Просто напиши мне свой вопрос в чат!",
        reply_markup=main_menu()
    )
