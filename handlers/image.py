from aiogram import Router, types, F
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from . import helpers
import logging, requests, os, time
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

router = Router()
logger = logging.getLogger(__name__)

API_KEY = os.getenv('OPENAI_API_KEY')
PROMPT_MODEL = "gpt-4.1-nano"

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

    if not API_KEY:
        return await message.answer("❌ API ключ не настроен")

    status_msg = await message.answer("🎨 Генерирую картинку...")

    try:
        # ===== 1. УЛУЧШЕНИЕ ПРОМПТА ЧЕРЕЗ GPT =====
        logger.info(f"🔄 [{user_id}] Улучшение промпта...")
        prompt_resp = requests.post(
            "https://openai.bothub.chat/v1/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": PROMPT_MODEL,
                "messages": [
                    {"role": "system", "content": "Create detailed English prompt for image generation. Only the prompt!"},
                    {"role": "user", "content": f"Prompt for: {prompt}"}
                ],
                "max_tokens": 200
            },
            timeout=30
        )
        enhanced = prompt
        if prompt_resp.status_code == 200:
            enhanced = prompt_resp.json().get('choices', [{}])[0].get('message', {}).get('content', prompt).strip('"')
            logger.info(f"✅ [{user_id}] Промпт улучшен: {enhanced[:50]}...")

        # ===== 2. ГЕНЕРАЦИЯ ЧЕРЕЗ REPLICATE =====
        logger.info(f"🔄 [{user_id}] Запрос к Replicate...")
        img_resp = requests.post(
            "https://bothub.chat/api/v2/replicate/v1/images/generations",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": model_config["api_model"],
                "input": {
                    "prompt": enhanced,
                    "aspect_ratio": "1:1",
                    "output_format": "webp"
                },
                "bothub": {"include_usage": True, "return_base64": False}
            },
            timeout=60
        )
        
        img_data = None
        
        if img_resp.status_code == 200:
            result = img_resp.json()
            img_url = result.get('url')
            if isinstance(img_url, list):
                img_url = img_url[0]
            
            if img_url:
                logger.info(f"✅ [{user_id}] URL получен")
                img_response = requests.get(img_url, timeout=30)
                if img_response.status_code == 200 and len(img_response.content) > 1000:
                    img_data = img_response.content
                    logger.info(f"✅ [{user_id}] Картинка скачана, размер: {len(img_data)} байт")
        else:
            logger.error(f"❌ [{user_id}] Replicate ошибка: {img_resp.status_code}")

        if img_data:
            # ===== 3. ВОДЯНОЙ ЗНАК =====
            try:
                img = Image.open(BytesIO(img_data))
                draw = ImageDraw.Draw(img)
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
                except:
                    font = ImageFont.load_default()
                draw.text((10, 10), "Vertex AI", font=font, fill=(255, 255, 255, 128))
                output = BytesIO()
                img.save(output, format='PNG')
                output.seek(0)
                img_data = output.getvalue()
            except Exception as e:
                logger.warning(f"⚠️ [{user_id}] Водяной знак: {e}")

            # ===== 4. СПИСЫВАЕМ ТОКЕНЫ =====
            spend_tokens(user_id, price)
            
            # ===== 5. СОХРАНЯЕМ В БД =====
            image_id = None
            session_id = None
            for attempt in range(3):
                try:
                    image_id, session_id = save_image_to_history(
                        user_id=user_id,
                        prompt=prompt,
                        enhanced_prompt=enhanced,
                        model=model_config["api_model"],
                        image_data=img_data
                    )
                    logger.info(f"✅ [{user_id}] Сохранено в БД: image_id={image_id}")
                    break
                except Exception as e:
                    if "database is locked" in str(e) and attempt < 2:
                        time.sleep(1)
                        continue
                    logger.error(f"❌ [{user_id}] Ошибка БД: {e}")
                    break

            new_tokens = get_tokens(user_id)
            
            # ===== 6. КНОПКИ =====
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✏️ Поправить", callback_data=f"edit_{image_id}")],
                [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
            ]) if image_id else helpers.main_menu()
            
            # ===== 7. ОТПРАВЛЯЕМ =====
            await message.answer_photo(
                BufferedInputFile(file=img_data, filename="image.png"),
                caption=f"🖼️ **Твоя картинка**\n📝 {prompt[:50]}\n🤖 {model_config['name']}\n💰 -{price} токенов | 🪙 {new_tokens} осталось",
                reply_markup=keyboard
            )
            await status_msg.delete()
            logger.info(f"✅ [{user_id}] Картинка отправлена")
            return

        await status_msg.edit_text("❌ Не удалось получить картинку")
        
    except Exception as e:
        logger.error(f"❌ [{user_id}] Ошибка: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")

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

@router.callback_query(F.data.startswith("edit_"))
async def edit_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    image_id = int(callback.data.replace("edit_", ""))
    
    image = get_image_by_id(image_id)
    if not image:
        await callback.answer("❌ Картинка не найдена", show_alert=True)
        return
    
    helpers.user_pages[user_id] = {"state": "waiting_edit", "image_id": image_id}
    
    await callback.message.answer(
        "✏️ **Что изменить?**\n\n"
        "Напиши, что хочешь поменять:\n"
        "• *сделай кота чёрным*\n"
        "• *добавь шляпу*\n"
        "• *убери фон*\n\n"
        "⏹ /cancel",
        reply_markup=helpers.edit_in_progress_kb()
    )
    await callback.answer()
