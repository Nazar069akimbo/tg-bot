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
    if user_id is None:
        user_id = message.from_user.id
    if not prompt:
        prompt = message.text

    ask_model = get_setting(f"ask_image_model_{user_id}") != "no"

    if ask_model:
        user = get_user(user_id)
        plan = dict(user).get("plan", "basic") if user else "basic"
        balance = get_tokens(user_id)
        img_used, img_limit = get_week_images_used(user_id)
        current_model = get_model_setting("image_generate") or "flux-schnell"

        await message.answer(
            f"🎨 Выбери модель ({img_used}/{img_limit}):",
            reply_markup=helpers.model_choice_kb("image_generate", current_model, plan, balance)
        )
        helpers.user_pages[user_id] = {"state": "waiting_image_model", "pending_prompt": prompt}
        return

    current_model = get_model_setting("image_generate") or "flux-schnell"
    image_cost = helpers.MODEL_COSTS.get(current_model, 10)

    if not helpers.can_use_model(user_id, current_model):
        await message.answer(f"🔒 Модель {helpers.MODEL_NAMES.get(current_model)} доступна только на Premium или с токенами.\n\nОформи: /credits")
        return

    balance = get_tokens(user_id)

    if balance > 0:
        if balance < image_cost:
            await message.answer(f"❌ Не хватает токенов: нужно {image_cost}, у тебя {balance}.\n\nПополни: /credits")
            return
        spend_tokens(user_id, image_cost)
    else:
        img_used, img_limit = get_week_images_used(user_id)
        if img_used >= img_limit:
            await message.answer(f"🔒 Лимит картинок на неделю исчерпан ({img_used}/{img_limit}).\n\n💎 Купи токены: /credits")
            return
        use_week_image(user_id)

    if not API_KEY:
        return await message.answer("❌ API ключ не настроен")

    status_msg = await message.answer("🎨 Рисую картинку...")

    try:
        # 1. Улучшение промпта
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
            logger.info(f"✅ [{user_id}] Промпт: {enhanced[:60]}")

        # 2. Генерация картинки
        logger.info(f"🎨 [{user_id}] Запрос к Replicate: model={current_model}")
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

        logger.info(f"📡 [{user_id}] Статус: {img_resp.status_code}")
        logger.info(f"📦 [{user_id}] Ответ: {img_resp.text[:800]}")

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
            logger.error(f"❌ [{user_id}] Ошибка генерации: {img_resp.status_code}")
            # Показываем пользователю текст ошибки
            try:
                err_text = img_resp.json().get('detail') or img_resp.json().get('error') or img_resp.text[:200]
            except Exception:
                err_text = img_resp.text[:200]
            await status_msg.edit_text(
                f"❌ Ошибка генерации ({img_resp.status_code})\n\n"
                f"Модель: {current_model}\n"
                f"Ответ: {err_text[:200]}"
            )
            return

        if img_data:
            # 3. Водяной знак
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

            # 4. Сохранение
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
                    logger.warning(f"⚠️ [{user_id}] Папка: {e}")
            except Exception as e:
                logger.warning(f"⚠️ [{user_id}] БД: {e}")

            # 5. Отправка
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Ещё", callback_data="regenerate"),
                 InlineKeyboardButton(text="🎨 Стикер", callback_data="make_sticker")],
                [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
            ])

            await message.answer_photo(
                BufferedInputFile(file=img_data, filename="image.png"),
                caption=f"🖼️ Твоя картинка\n📝 {prompt[:50]}\n🤖 {helpers.MODEL_NAMES.get(current_model, current_model)}\n💰 -{image_cost} токенов",
                reply_markup=keyboard
            )
            await status_msg.delete()
            logger.info(f"✅ [{user_id}] Картинка отправлена")
            return

        await status_msg.edit_text(f"❌ Не удалось получить картинку")

    except Exception as e:
        logger.error(f"❌ [{user_id}] Ошибка: {e}", exc_info=True)
        try:
            await status_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
        except Exception:
            pass


@router.callback_query(F.data == "back_to_main")
async def back_main_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    name = helpers.get_user_name(user_id) or "друг"
    text = f"✨ Vertex AI\n\n👋 Привет, {name}!\n\n📧 Проблемы? Пиши: mychannell@gmail.com"
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
