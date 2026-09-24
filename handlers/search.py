from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import *
from ai.client import solve_problem
from utils.search import search_duckduckgo
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("search"))
async def search_command(message: types.Message):
    user_id = message.from_user.id
    query = message.text.replace("/search", "").strip()
    
    if not query:
        await message.answer("❌ Напиши: /search что искать")
        return
    
    status = await message.answer(f"🔍 Ищу: {query}...")
    
    result = search_duckduckgo(query)
    
    if result:
        await status.edit_text(f"🔍 **Результат:**\n\n{result}")
    else:
        answer = solve_problem(f"Найди информацию про: {query}", "chat", False)
        await status.edit_text(f"🔍 **Поиск:**\n\n{answer}")
