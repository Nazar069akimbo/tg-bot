from aiogram import Router, types
from aiogram.filters import Command
from ai.client import search_web
import logging

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("search"))
async def search_command(message: types.Message):
    query = message.text.replace("/search", "").strip()
    if not query:
        await message.answer("❌ Напиши: /search что искать")
        return

    status = await message.answer(f"🔍 Ищу: {query}...")
    result = search_web(query)
    await status.edit_text(f"🔍 Результат:\n\n{result}")
