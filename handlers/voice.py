from aiogram import Router, types, F
from database.db import *
from ai.client import solve_problem
import openai, os, logging

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
        
        openai.api_key = API_KEY
        openai.base_url = 'https://openai.bothub.chat/v1'
        
        transcript = openai.Audio.transcribe(
            model="whisper-1",
            file=voice_content
        )
        
        text = transcript.text
        await status.edit_text(f"🎤 **Распознано:**\n{text}")
        
        answer = solve_problem(text, "chat", False)
        await message.answer(answer)
        add_to_context(user_id, text)
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)[:100]}")
