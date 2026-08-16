from aiogram import Router, types, F
from aiogram.types import BufferedInputFile
from database.db import *
from . import helpers
import logging, requests, json, time, asyncio, os
from io import BytesIO
from openai import OpenAI

router = Router()
logger = logging.getLogger(__name__)

API_KEY = os.getenv('OPENAI_API_KEY')
PROMPT_MODEL = "gpt-4.1-nano"

# Исправленный клиент
if API_KEY:
    client = OpenAI(
        api_key=API_KEY,
        base_url='https://openai.bothub.chat/v1',
        http_client=None  # ← Добавляем http_client=None
    )
else:
    client = None

async def generate_image(message: types.Message, prompt=None):
    user_id = message.from_user.id
    logger.info(f"📌 [{user_id}] generate_image")
    
    if not prompt:
        prompt = message.text

    model_config = helpers.get_model_config(user_id)
    price = model_config["price"]

    tokens = get_tokens(user_id)
    if tokens < price:
        await message.answer(f"❌ Недостаточно токенов! Нужно: {price}, у тебя: {tokens}")
        return

    if not API_KEY or not client:
        return await message.answer("❌ API ключ не настроен")

    status_msg = await message.answer("🎨 Генерирую...")

    try:
        # Улучшение промпта
        prompt_resp = requests.post(
            "https://openai.bothub.chat/v1/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": PROMPT_MODEL,
                "messages": [
                    {"role": "system", "content": "Create detailed English prompt. Only the prompt!"},
                    {"role": "user", "content": f"Prompt for: {prompt}"}
                ],
                "max_tokens": 200
            },
            timeout=30
        )
        enhanced = prompt
        if prompt_resp.status_code == 200:
            enhanced = prompt_resp.json().get('choices', [{}])[0].get('message', {}).get('content', prompt).strip('"')

        img_data = None
        
        # OpenAI
        try:
            params = {
                'model': model_config["api_model"],
                'prompt': enhanced,
                'n': 1,
                'size': '1024x1024',
            }
            req = client.images.generate(**params)
            if hasattr(req, 'data') and len(req.data) > 0:
                image_url = req.data[0].url
                if image_url:
                    img_data_response = requests.get(image_url, timeout=30)
                    if img_data_response.status_code == 200:
                        img_data = img_data_response.content
        except Exception as e:
            logger.error(f"OpenAI ошибка: {e}")
            # Fallback Replicate
            img_resp = requests.post(
                "https://bothub.chat/api/v2/replicate/v1/images/generations",
                headers={"Authorization": f"Bearer {API_KEY}"},
                json={
                    "model": model_config["api_model"],
                    "input": {"prompt": enhanced, "aspect_ratio": "1:1", "output_format": "webp"}
                },
                timeout=120
            )
            if img_resp.status_code == 200:
                img_url = img_resp.json().get('url')
                if img_url:
                    img_data_response = requests.get(img_url, timeout=30)
                    if img_data_response.status_code == 200:
                        img_data = img_data_response.content

        if img_data:
            img_data = helpers.add_watermark(img_data)
            spend_tokens(user_id, price)
            image_id, session_id = save_image_to_history(
                user_id=user_id, prompt=prompt, enhanced_prompt=enhanced,
                model=model_config["api_model"], image_data=img_data
            )
            new_tokens = get_tokens(user_id)
            await message.answer_photo(
                BufferedInputFile(file=img_data, filename="image.png"),
                caption=f"🖼️ **Твоя картинка**\n📝 {prompt[:50]}\n💰 -{price} токенов | 🪙 {new_tokens} осталось",
                reply_markup=helpers.image_action_buttons(image_id, session_id)
            )
            await status_msg.delete()
            return

        await status_msg.edit_text("❌ Не удалось получить картинку")
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

@router.callback_query(F.data == "back_to_main")
async def back_main_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    tokens = get_tokens(user_id)
    name = helpers.get_user_name(user_id) or "друг"
    await callback.message.edit_text(
        f"✨ **Vertex AI**\n\n👋 Привет, {name}!\n💰 Токенов: {tokens}",
        reply_markup=helpers.main_menu()
    )
    await helpers.safe_answer(callback)
