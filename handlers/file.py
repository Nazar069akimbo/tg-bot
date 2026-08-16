from aiogram import Router, types, F
from database.db import *
from ai.client import solve_problem
from utils.file_parser import parse_file
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.message(F.document)
async def handle_file(message: types.Message):
    user_id = message.from_user.id
    doc = message.document
    
    ext = doc.file_name.split('.')[-1].lower()
    if ext not in ['pdf', 'docx', 'txt', 'csv']:
        await message.answer("❌ Поддерживаются: PDF, DOCX, TXT, CSV")
        return
    
    status = await message.answer(f"📄 Анализирую {doc.file_name}...")
    
    try:
        file = await message.bot.get_file(doc.file_id)
        file_content = await message.bot.download_file(file.file_path)
        
        text = parse_file(file_content.read(), ext)
        
        if not text:
            await status.edit_text("❌ Не удалось извлечь текст")
            return
        
        answer = solve_problem(f"Проанализируй текст и дай краткое резюме:\n{text[:3000]}", "chat", False)
        await status.edit_text(f"📊 **Анализ файла:**\n\n{answer}")
        add_to_context(user_id, f"Анализ файла {doc.file_name}")
        
    except Exception as e:
        await status.edit_text(f"❌ Ошибка: {str(e)[:100]}")
