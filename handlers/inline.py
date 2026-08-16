from aiogram import Router, types
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.inline_query()
async def inline_handler(query: types.InlineQuery):
    user_id = query.from_user.id
    text = query.query or ""
    
    if not text:
        await query.answer([
            types.InlineQueryResultArticle(
                id="help",
                title="Напиши запрос",
                description="Например: кот, пейзаж...",
                input_message_content=types.InputTextMessageContent(
                    message_text="Напиши что-нибудь, чтобы я сгенерировал картинку!"
                )
            )
        ], cache_time=1)
        return
    
    # Базовая реализация inline-режима
    await query.answer([
        types.InlineQueryResultArticle(
            id="result",
            title=f"Генерация: {text[:30]}",
            description="Нажми, чтобы получить результат",
            input_message_content=types.InputTextMessageContent(
                message_text=f"🖼️ Генерирую картинку по запросу: {text}\n\nОжидайте..."
            )
        )
    ], cache_time=1)
