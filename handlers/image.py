from aiogram import Router, types, F
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from . import helpers
import logging, requests, os
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

router = Router()
logger = logging.getLogger(__name__)

API_KEY = os.getenv('OPENAI_API_KEY')
PROMPT_MODEL = "gpt-4.1-nano"


async def generate_image(message: types.Message, prompt=None, user_id: int = None):
    logger.info(f"🖼️ generate_image ВЫЗВАН: user_id={user_id}, prompt={prompt[:50] if prompt else None}")

    if user_id is None:
        user_id = message.from_user.id
    if not prompt:
        prompt = message.text

    # Проверка: спрашивать ли модель
    ask_model = get_setting(f"ask_image_model_{user_id}") != "no"
    logger.info(f"🖼️ ask_model={ask_model}")

    if ask_model:
        user = get_user(user_id)
        plan = dict(user).get("plan", "basic") if user else "basic"
        used, limit = get_daily_usage(user_id)
        balance = limit - used
        current_model = get_model_setting("image_generate") or "flux-schnell"

        logger.info(f"🖼️ Показываю выбор модели, current={current_model}")
        await message.answer(
            f"🎨 Выбери модель ({balance}/{limit} запросов):",
            reply_markup=helpers.model_choice_kb("image_generate", current_model, plan, balance)
        )
        helpers.user_pages[user_id] = {"state": "waiting_image_model", "pending_prompt": prompt}
        return

    # Проверка доступа
    user = get_user(user_id)
    plan = dict(user).get("plan", "basic") if user else "basic"
    current_model = get_model_setting("image_generate") or "flux-schnell"
    image_cost = helpers.MODEL_COSTS.get(current_model, 10)

    logger.info(f"🖼️ Проверка: model={current_model}, cost={image_cost}")

    user_level = helpers.PLAN_LEVEL.get(plan, 0)
    required = helpers.MODEL_MIN_LEVEL.get(current_model, 0)

    if required > user_level:
        await message.answer(f"🔒 Модель {helpers.MODEL_NAMES.get(current_model)} только на Premium.\nОформи: /credits")
        return

    # Проверка лимита
    used, limit = get_daily_usage(user_id)
    if used + 1 > limit:
        await message.answer(f"🔒 Лимит исчерпан ({used}/{limit}).")
        return

    # Проверка токенов
    tokens = get_tokens(user_id)
    if tokens < image_cost:
        await message.answer(f"❌ Нужно {image_cost} токенов, у тебя {tokens}")
        return

    if not API_KEY:
        return await message.answer("❌ API ключ не настроен")

    logger.info(f"🖼️ Списание запроса и запуск генерации")
    spend_daily_requests(user_id, 1)

    status_msg = await message.answer("🎨 Рисую картинку...")

    try:
        # Улучшение промпта
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

        logger.info(f"🖼️ Запрос к Replicate: model={current_model}")
        img_resp = requests.post(
            "https://bothub.chat/api/v2/replicate/v1/images/generations",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": current_model,
                "input": {"prompt": enhanced, "aspect_ratio": "1:1", "output_format": "webp"},
                "bothub": {"include_usage": True, "return_base64": False}
            },
            timeout=120
        )

        logger.info(f"🖼️ Статус ответа: {img_resp.status_code}")
        logger.info(f"🖼️ Ответ: {img_resp.text[:300]}")

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
                except Exception as e:
                    logger.error(f"❌ Скачивание: {e}")
        else:
            logger.error(f"❌ Replicate: {img_resp.status_code} - {img_resp.text[:200]}")

        if img_data:
            # Водяной знак
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
                logger.warning(f"⚠️ Водяной знак: {e}")

            spend_tokens(user_id, image_cost)
            new_tokens = get_tokens(user_id)

            image_id = None
            try:
                image_id, session_id = save_image_to_history(
                    user_id=user_id, prompt=prompt, enhanced_prompt=enhanced,
                    model=current_model, image_data=img_data
                )
                try:
                    from utils.user_storage import save_user_image, update_meta
                    save_user_image(user_id, image_id, img_data)
                    update_meta(user_id, last_topics=[prompt[:50]])
                except Exception as e:
                    logger.warning(f"⚠️ Папка: {e}")
            except Exception as e:
                logger.warning(f"⚠️ БД: {e}")

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Ещё", callback_data="regenerate"),
                 InlineKeyboardButton(text="🎨 Стикер", callback_data="make_sticker")],
                [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
            ])

            await message.answer_photo(
                BufferedInputFile(file=img_data, filename="image.png"),
                caption=f"🖼️ Твоя картинка\n📝 {prompt[:50]}\n🤖 {helpers.MODEL_NAMES.get(current_model, current_model)}\n💰 -{image_cost} токенов | 🪙 {new_tokens}",
                reply_markup=keyboard
            )
            await status_msg.delete()
            logger.info(f"✅ [{user_id}] Картинка отправлена")
            return

        await status_msg.edit_text(f"❌ Не удалось. Код: {img_resp.status_code}")

    except Exception as e:
        logger.error(f"❌ [{user_id}] Ошибка: {e}", exc_info=True)
        try:
            await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        except Exception:
            pass


@router.callback_query(F.data == "back_to_main")
async def back_main_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    tokens = get_tokens(user_id)
    name = helpers.get_user_name(user_id) or "друг"
    text = f"✨ Vertex AI\n\n👋 Привет, {name}!\n💰 Токенов: {tokens}\n\n📧 Проблемы? Пиши: mychannell@gmail.com"
    try:
        await callback.message.edit_text(text, reply_markup=helpers.main_menu())
    except Exception:
        await callback.message.answer(text, reply_markup=helpers.main_menu())
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "regenerate")
async def regenerate_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    memory = get_user_memory(user_id)
    if memory and memory.get('context_history'):
        import json
        history = json.loads(memory.get('context_history', '[]'))
        if history:
            prompt = history[-1].get('prompt', '')
            if prompt:
                await callback.message.answer("🔄 Генерирую вариацию...")
                await generate_image(callback.message, prompt, user_id)
                await callback.answer()
                return
    await callback.answer("❌ Не найден запрос", show_alert=True)


@router.callback_query(F.data == "make_sticker")
async def make_sticker_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    memory = get_user_memory(user_id)
    if memory and memory.get('context_history'):
        import json
        history = json.loads(memory.get('context_history', '[]'))
        if history:
            prompt = history[-1].get('prompt', '')
            if prompt:
                await callback.message.answer("🎨 Делаю стикер...")
                await generate_image(callback.message, f"{prompt}, as a sticker, white border", user_id)
                await callback.answer()
                return
    await callback.answer("❌ Не найден запрос", show_alert=True)
