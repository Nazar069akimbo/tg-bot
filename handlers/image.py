from aiogram import Router, types, F
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from . import helpers
import logging, requests, json, os, time
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from openai import OpenAI

router = Router()
logger = logging.getLogger(__name__)

API_KEY = os.getenv('OPENAI_API_KEY')

async def generate_image(message: types.Message, prompt=None):
    """
    Генерация картинки через OpenAI-совместимый клиент Bothub
    """
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
        # === ИСПОЛЬЗУЕМ OPENAI-КЛИЕНТ ===
        client = OpenAI(
            api_key=API_KEY,
            base_url='https://openai.bothub.chat/v1'
        )
        
        # Параметры для генерации
        params = {
            'model': model_config["api_model"],  # 'flux-schnell'
            'prompt': prompt,
            'n': 1,
            'size': '1024x1024',
        }
        
        logger.info(f"🔄 [{user_id}] Запрос к OpenAI API...")
        response = client.images.generate(**params)
        
        # Логируем ответ для отладки
        logger.info(f"✅ [{user_id}] Ответ получен: {response.model_dump_json()[:200]}...")
        
        # Извлекаем URL
        if hasattr(response, 'data') and len(response.data) > 0:
            image_url = response.data[0].url
            logger.info(f"✅ [{user_id}] URL получен: {image_url[:50]}...")
        else:
            raise ValueError("Нет data в ответе OpenAI")
        
        if not image_url:
            raise ValueError("URL картинки не получен")
        
        # === СКАЧИВАЕМ КАРТИНКУ ===
        logger.info(f"🔄 [{user_id}] Скачивание картинки...")
        headers = {"Authorization": f"Bearer {API_KEY}"}
        img_response = requests.get(image_url, headers=headers, timeout=30)
        
        if img_response.status_code != 200:
            raise ValueError(f"Ошибка скачивания: {img_response.status_code}")
        
        if len(img_response.content) < 1000:
            raise ValueError(f"Картинка слишком маленькая: {len(img_response.content)} байт")
        
        img_data = img_response.content
        logger.info(f"✅ [{user_id}] Картинка скачана, размер: {len(img_data)} байт")

        # === ВОДЯНОЙ ЗНАК ===
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
            logger.warning(f"⚠️ [{user_id}] Не удалось наложить водяной знак: {e}")

        # === СПИСЫВАЕМ ТОКЕНЫ ===
        spend_tokens(user_id, price)
        
        # === СОХРАНЯЕМ В БД ===
        image_id = None
        session_id = None
        for attempt in range(3):
            try:
                image_id, session_id = save_image_to_history(
                    user_id=user_id,
                    prompt=prompt,
                    enhanced_prompt=prompt,
                    model=model_config["api_model"],
                    image_data=img_data
                )
                logger.info(f"✅ [{user_id}] Сохранено в БД: image_id={image_id}")
                break
            except Exception as e:
                if "database is locked" in str(e) and attempt < 2:
                    time.sleep(1)
                    continue
                logger.error(f"❌ [{user_id}] Ошибка сохранения в БД: {e}")
                break

        new_tokens = get_tokens(user_id)
        
        # === КНОПКИ ===
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Поправить", callback_data=f"edit_{image_id}")],
            [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
        ]) if image_id else helpers.main_menu()
        
        # === ОТПРАВЛЯЕМ ===
        await message.answer_photo(
            BufferedInputFile(file=img_data, filename="image.png"),
            caption=f"🖼️ **Твоя картинка**\n📝 {prompt[:50]}\n💰 -{price} токенов | 🪙 {new_tokens} осталось",
            reply_markup=keyboard
        )
        await status_msg.delete()
        logger.info(f"✅ [{user_id}] Картинка отправлена пользователю")
        return

    except Exception as e:
        logger.error(f"❌ [{user_id}] Ошибка генерации: {e}", exc_info=True)
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
    """Обработка нажатия на кнопку 'Поправить'"""
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
