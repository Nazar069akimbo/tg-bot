from aiogram import Router, types, F
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from . import helpers
import logging, requests, json, os, time
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
        # Генерация через Replicate
        img_resp = requests.post(
            "https://bothub.chat/api/v2/replicate/v1/images/generations",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": model_config["api_model"],
                "input": {
                    "prompt": prompt,
                    "aspect_ratio": "1:1",
                    "output_format": "webp"
                },
                "bothub": {"include_usage": True, "return_base64": False}
            },
            timeout=120
        )
        
        img_data = None
        
        if img_resp.status_code == 200:
            result = img_resp.json()
            img_url = result.get('url')
            if isinstance(img_url, list):
                img_url = img_url[0]
            if img_url:
                img_data_response = requests.get(img_url, timeout=30)
                if img_data_response.status_code == 200 and len(img_data_response.content) > 1000:
                    img_data = img_data_response.content

        if img_data:
            # Водяной знак
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
            except:
                pass

            spend_tokens(user_id, price)
            
            # === СОХРАНЯЕМ В БД ===
            image_id = None
            session_id = None
            for attempt in range(3):
                try:
                    image_id, session_id = save_image_to_history(
                        user_id=user_id, prompt=prompt, enhanced_prompt=prompt,
                        model=model_config["api_model"], image_data=img_data
                    )
                    logger.info(f"✅ [{user_id}] Сохранено в БД: image_id={image_id}, session_id={session_id}")
                    break
                except Exception as e:
                    if "database is locked" in str(e) and attempt < 2:
                        time.sleep(1)
                        continue
                    logger.error(f"Ошибка сохранения в БД: {e}")
                    break
            
            new_tokens = get_tokens(user_id)
            
            # === КНОПКИ С ПРАВКОЙ ===
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✏️ Поправить", callback_data=f"edit_{image_id}")],
                [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
            ]) if image_id else helpers.main_menu()
            
            await message.answer_photo(
                BufferedInputFile(file=img_data, filename="image.png"),
                caption=f"🖼️ **Твоя картинка**\n📝 {prompt[:50]}\n💰 -{price} токенов | 🪙 {new_tokens} осталось",
                reply_markup=keyboard
            )
            await status_msg.delete()
            return

        await status_msg.edit_text("❌ Не удалось получить картинку")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
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

@router.callback_query(F.data.startswith("edit_"))
async def edit_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    image_id = int(callback.data.replace("edit_", ""))
    
    logger.info(f"📌 [{user_id}] edit_callback: image_id={image_id}")
    
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
