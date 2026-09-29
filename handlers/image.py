from aiogram import Router, types, F
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from . import helpers
import logging, requests, os, json, random
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

router = Router()
logger = logging.getLogger(__name__)

API_KEY = os.getenv('OPENAI_API_KEY')
PROMPT_MODEL = "gpt-4.1-nano"

# Случайные вариации для кнопки «Ещё»
VARIATIONS = [
    "in a different style, cinematic lighting",
    "with soft pastel colors, dreamy atmosphere",
    "with bold neon colors, cyberpunk vibe",
    "in watercolor style, artistic brushstrokes",
    "as a sticker, kawaii chibi style, white outline",
    "in 3D render, Pixar style, soft shadows",
    "as pixel art, retro 8-bit style",
    "with dramatic lighting, high contrast",
    "in anime style, detailed lineart",
    "as a flat vector illustration, minimalist",
    "with golden hour lighting, warm tones",
    "in monochrome with one accent color",
]

STICKER_PROMPT = "as a sticker, die-cut, white border, vibrant colors, centered composition"


def _get_variation(times: int = 1) -> str:
    """Берёт случайную вариацию (можно несколько подряд)."""
    return ", ".join(random.sample(VARIATIONS, min(times, len(VARIATIONS))))


async def generate_image(message: types.Message, prompt=None, user_id: int = None, variation: bool = False, sticker: bool = False):
    if user_id is None:
        user_id = message.from_user.id

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
        # ===== 1. УЛУЧШЕНИЕ ПРОМПТА + ВАРИАЦИЯ =====
        base_prompt = prompt
        if variation:
            base_prompt = f"{prompt}, {_get_variation(2)}"
        if sticker:
            base_prompt = f"{prompt}, {STICKER_PROMPT}"

        logger.info(f"🔄 [{user_id}] Улучшение промпта (variation={variation}, sticker={sticker})...")
        prompt_resp = requests.post(
            "https://openai.bothub.chat/v1/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": PROMPT_MODEL,
                "messages": [
                    {"role": "system", "content": "Create detailed English prompt for image generation. Only the prompt!"},
                    {"role": "user", "content": f"Prompt for: {base_prompt}"}
                ],
                "max_tokens": 200
            },
            timeout=30
        )
        enhanced = base_prompt
        if prompt_resp.status_code == 200:
            enhanced = prompt_resp.json().get('choices', [{}])[0].get('message', {}).get('content', base_prompt).strip('"')
            logger.info(f"✅ [{user_id}] Промпт улучшен: {enhanced[:60]}...")

        # ===== 2. ГЕНЕРАЦИЯ =====
        logger.info(f"🔄 [{user_id}] Запрос к Replicate...")

        replicate_input = {
            "prompt": enhanced,
            "aspect_ratio": "1:1",
            "output_format": "webp"
        }
        # Стикерпак — квадратный, с прозрачным фоном
        if sticker:
            replicate_input["aspect_ratio"] = "1:1"

        try:
            img_resp = requests.post(
                "https://bothub.chat/api/v2/replicate/v1/images/generations",
                headers={"Authorization": f"Bearer {API_KEY}"},
                json={
                    "model": model_config["api_model"],
                    "input": replicate_input,
                    "bothub": {"include_usage": True, "return_base64": False}
                },
                timeout=120
            )
        except requests.exceptions.Timeout:
            logger.error(f"❌ [{user_id}] Таймаут Replicate")
            await status_msg.edit_text("⏳ Генерация занимает больше времени. Попробуйте ещё раз.")
            return
        except Exception as e:
            logger.error(f"❌ [{user_id}] Ошибка Replicate: {e}")
            await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")
            return

        img_data = None
        if img_resp.status_code == 200:
            result = img_resp.json()
            img_url = result.get('url')
            if isinstance(img_url, list):
                img_url = img_url[0]
            if img_url:
                try:
                    img_response = requests.get(img_url, timeout=30)
                    if img_response.status_code == 200 and len(img_response.content) > 1000:
                        img_data = img_response.content
                        logger.info(f"✅ [{user_id}] Картинка: {len(img_data)} байт")
                except Exception as e:
                    logger.error(f"❌ [{user_id}] Скачивание: {e}")
        else:
            logger.error(f"❌ [{user_id}] Replicate: {img_resp.status_code} - {img_resp.text[:200]}")

        if img_data:
            # ===== 3. ВОДЯНОЙ ЗНАК =====
            try:
                img = Image.open(BytesIO(img_data))
                draw = ImageDraw.Draw(img)
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
                except Exception:
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
            new_tokens = get_tokens(user_id)

            # ===== 5. СОХРАНЯЕМ В БД + ПАПКУ =====
            image_id = None
            try:
                image_id, session_id = save_image_to_history(
                    user_id=user_id,
                    prompt=prompt,
                    enhanced_prompt=enhanced,
                    model=model_config["api_model"],
                    image_data=img_data
                )
                add_to_context(user_id, prompt, image_id, None)

                try:
                    from utils.user_storage import save_user_image, update_meta
                    save_user_image(user_id, image_id, img_data)
                    update_meta(user_id, last_topics=[prompt[:50]])
                except Exception as e:
                    logger.warning(f"⚠️ [{user_id}] Папка: {e}")

            except Exception as e:
                logger.warning(f"⚠️ [{user_id}] БД: {e}")

            # ===== 6. ОТПРАВЛЯЕМ =====
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Ещё", callback_data="regenerate"),
                 InlineKeyboardButton(text="🎨 Стикер", callback_data="make_sticker")],
                [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
            ])

            await message.answer_photo(
                BufferedInputFile(file=img_data, filename="image.png"),
                caption=f"🖼️ **Твоя картинка**\n📝 {prompt[:50]}\n🤖 {model_config['name']}\n💰 -{price} токенов | 🪙 {new_tokens}",
                reply_markup=keyboard
            )
            await status_msg.delete()
            return

        await status_msg.edit_text("❌ Не удалось получить картинку. Попробуйте позже.")

    except Exception as e:
        logger.error(f"❌ [{user_id}] Ошибка: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")


@router.callback_query(F.data == "back_to_main")
async def back_main_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    tokens = get_tokens(user_id)
    name = helpers.get_user_name(user_id) or "друг"
    text = f"✨ **Vertex AI**\n\n👋 Привет, {name}!\n💰 Токенов: {tokens}"
    try:
        await callback.message.edit_text(text, reply_markup=helpers.main_menu())
    except Exception:
        await callback.message.answer(text, reply_markup=helpers.main_menu())
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "regenerate")
async def regenerate_cb(callback: types.CallbackQuery):
    """Ещё — тот же промпт, но со случайной вариацией."""
    user_id = callback.from_user.id
    memory = get_user_memory(user_id)
    if memory and memory.get('context_history'):
        history = json.loads(memory.get('context_history', '[]'))
        if history:
            last = history[-1]
            prompt = last.get('prompt', '')
            if prompt:
                await callback.message.answer("🔄 Генерирую вариацию...")
                await generate_image(callback.message, prompt, user_id, variation=True)
                await callback.answer()
                return
    await callback.answer("❌ Не найден предыдущий запрос", show_alert=True)


@router.callback_query(F.data == "make_sticker")
async def make_sticker_cb(callback: types.CallbackQuery):
    """Стикер — тот же промпт, но в стиле стикера."""
    user_id = callback.from_user.id
    memory = get_user_memory(user_id)
    if memory and memory.get('context_history'):
        history = json.loads(memory.get('context_history', '[]'))
        if history:
            last = history[-1]
            prompt = last.get('prompt', '')
            if prompt:
                await callback.message.answer("🎨 Делаю стикер...")
                await generate_image(callback.message, prompt, user_id, sticker=True)
                await callback.answer()
                return
    await callback.answer("❌ Не найден предыдущий запрос", show_alert=True)
