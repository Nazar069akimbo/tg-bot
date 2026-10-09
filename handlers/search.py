from aiogram import Router, types
from aiogram.filters import Command
from ai.client import smart_reply
import requests
import logging

router = Router()
logger = logging.getLogger(__name__)


def search_duckduckgo(query):
    """Реальный поиск через DuckDuckGo API."""
    try:
        resp = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get('AbstractText'):
                return data['AbstractText']
            if data.get('RelatedTopics'):
                for topic in data['RelatedTopics']:
                    if isinstance(topic, dict) and 'Text' in topic:
                        return topic['Text']
                    if isinstance(topic, dict) and 'Topics' in topic:
                        for t in topic['Topics']:
                            if 'Text' in t:
                                return t['Text']
        return None
    except Exception as e:
        logger.error(f"❌ DuckDuckGo: {e}")
        return None


@router.message(Command("search"))
async def search_command(message: types.Message):
    query = message.text.replace("/search", "").strip()
    if not query:
        await message.answer("❌ Напиши: /search что искать")
        return

    status = await message.answer(f"🔍 Ищу: {query}...")

    result = search_duckduckgo(query)

    if result:
        await status.edit_text(f"🔍 **Результат:**\n\n{result}")
    else:
        # Fallback — через ИИ
        ai_result = smart_reply(message.from_user.id, f"Ответь на вопрос: {query}")
        answer = ai_result.get("reply", "Не смог найти.")
        await status.edit_text(f"🔍 **Ответ:**\n\n{answer}")
