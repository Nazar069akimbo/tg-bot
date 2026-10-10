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
        current_model = get_model_setting("image_generate") or "flux-schnell"

        await message.answer(
            f"🎨 Выбери модель:",
            reply_markup=helpers.model_choice_kb("image_generate", current_model, plan, balance)
        )
        helpers.user_pages[user_id] = {"state": "waiting_image_model", "pending_prompt": prompt}
        return

    current_model = get_model_setting("image_generate") or "flux-schnell"
    image_cost = helpers.MODEL_COSTS.get(current_model, 10)

    if not helpers.can_use_model(user_id, current_model):
        await message.answer(
            f"🔒 Модель <b>{helpers.MODEL_NAMES.get(current_model)}</b> доступна только на Premium или с токенами.\n\n"
            f"💎 Оформи: /credits"
        )
        return

    balance = get_tokens(user_id)

    if balance < image_cost:
        await message.answer(
            f"❌ Не хватает токенов: нужно <b>{image_cost}</b>, у тебя <b>{balance}</b>.\n\n"
            f"💎 Пополни: /credits"
        )
        return
    spend_tokens(user_id, image_cost)

    if not API_KEY:
        return await message.answer("❌ API ключ не настроен")

    status_msg = await message.answer("🎨 Рисую картинку...")

    try:
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
            try:
                enhanced = prompt_resp.json()['choices'][0]['message']['content'].strip('"')
            except (KeyError, IndexError, TypeError):
                enhanced = prompt

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
        logger.info(f"📦 [{user_id}] Ответ: {img_resp.text[:300]}")

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
                    logger.error(f"❌ [{user_id}] Скачивание: {e}")

        if not img_data:
            err_text = "Неизвестная ошибка"
            try:
                data = img_resp.json()
                if isinstance(data.get('error'), dict):
                    err_text = data['error'].get('message', str(data['error']))
                elif data.get('detail'):
                    err_text = str(data['detail'])
                elif data.get('message'):
                    err_text = str(data['message'])
                else:
                    err_text = img_resp.text
            except Exception:
                err_text = img_resp.text
            err_text = str(err_text)[:300]

            await status_msg.edit_text(
                f"❌ Ошибка генерации ({img_resp.status_code})\n\n"
                f"Модель: {current_model}\n"
                f"Ответ: {err_text}"
            )
            return

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

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
        ])

        await message.answer_photo(
            BufferedInputFile(file=img_data, filename="image.png"),
            caption=(
                f"🖼️ <b>Твоя картинка</b>\n"
                f"📝 {prompt[:50]}\n"
                f"🤖 {helpers.MODEL_NAMES.get(current_model, current_model)}\n"
                f"💰 -{image_cost} токенов"
            ),
            reply_markup=keyboard
        )
        await status_msg.delete()
        logger.info(f"✅ [{user_id}] Картинка отправлена")

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
    text = f"✨ <b>Vertex AI</b>\n\n👋 Привет, <b>{name}</b>!\n\n📧 Проблемы? Пиши: mychannell069@gmail.com"
    try:
        await callback.message.edit_text(text, reply_markup=helpers.main_menu())
    except Exception:
        await callback.message.answer(text, reply_markup=helpers.main_menu())
    await helpers.safe_answer(callback)
