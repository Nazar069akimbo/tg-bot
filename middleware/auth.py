from aiogram import BaseMiddleware
from typing import Callable, Dict, Any, Awaitable
from aiogram.types import TelegramObject, Message, CallbackQuery
from database.db import get_user, cursor

class AuthMiddleware(BaseMiddleware):
    """Middleware для проверки авторизации"""
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
            user = get_user(user_id)
            if user:
                cursor.execute("SELECT is_blocked FROM users WHERE user_id = ?", (user_id,))
                result = cursor.fetchone()
                if result and result[0] == 1:
                    await event.answer("⛔ Вы заблокированы.")
                    return
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id
            user = get_user(user_id)
            if user:
                cursor.execute("SELECT is_blocked FROM users WHERE user_id = ?", (user_id,))
                result = cursor.fetchone()
                if result and result[0] == 1:
                    await event.answer("⛔ Вы заблокированы.")
                    return
        return await handler(event, data)
