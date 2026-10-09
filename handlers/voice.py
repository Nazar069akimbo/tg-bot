from aiogram import Router, types, F
from database.db import *
from ai.client import smart_reply
from openai import OpenAI
import os, logging

router = Router()
logger = logging.getLogger(__name__)

API_KEY = os.getenv('OPENAI_API_KEY')


@router.message(F.voice)
async def handle_voice(message: types.Message):
    user_id = message.from_user.id

    try:
        status = await message.answer("🎤 Распознаю голосовое...")

        voice = await message.bot.get_file(message.voice.file_id)
        voice_content = await message.bot.download_file(voice.file_path)

        if not API_KEY:
            await status.edit_text("❌ API ключ не настроен")
            return

        client = OpenAI(api_key=API_KEY, base_url='https://openai.bothub.chat/v1')

        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=voice_content
        )

        text = transcript.text
        await status.edit_text(f"🎤 Распознано:\n{text}")

        # ИИ отвечает
        result = smart_reply(user_id, text)
        answer = result.get("reply", "Не понял.")
        await message.answer(answer)

        # Добавляем в историю
        try:
            from utils.user_storage import append_history
            append_history(user_id, "user", text)
            append_history(user_id, "assistant", answer)
        except Exception as e:
            logger.warning(f"⚠️ История: {e}")

    except Exception as e:
        logger.error(f"❌ [{user_id}] Ошибка голосового: {e}")
        await message.answer(f"❌ Ошибка: {str(e)[:100]}")
