"""Логирование всех действий бота через middleware (не блокирует хендлеры).

Использование в bot.py:
    from handlers.logging_hub import setup_logging
    setup_logging(dp, logger)

Файл логов настраивается в bot.py (RotatingFileHandler -> logs/bot.log).
"""
import logging
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, InlineQuery


class LoggingMiddleware(BaseMiddleware):
    """Логирует каждое сообщение/колбэк/инлайн и НЕ мешает дальнейшей обработке."""

    def __init__(self, logger: logging.Logger):
        super().__init__()
        self.logger = logger

    async def __call__(self, handler, event, data):
        try:
            if isinstance(event, Message):
                user = event.from_user
                who = (user.full_name or user.username or str(user.id)) if user else "?"
                uid = user.id if user else "?"
                if event.text:
                    self.logger.info(f"MSG [{uid}] ({who}): {event.text[:200]!r}")
                elif event.caption:
                    self.logger.info(f"MSG [{uid}] ({who}) [{event.content_type}]: {event.caption[:200]!r}")
                else:
                    self.logger.info(f"MSG [{uid}] ({who}) type={event.content_type}")
            elif isinstance(event, CallbackQuery):
                user = event.from_user
                who = (user.full_name or user.username or str(user.id)) if user else "?"
                uid = user.id if user else "?"
                self.logger.info(f"CB  [{uid}] ({who}): data={event.data!r}")
            elif isinstance(event, InlineQuery):
                user = event.from_user
                uid = user.id if user else "?"
                self.logger.info(f"INL [{uid}]: query={event.query[:100]!r}")
        except Exception as e:
            self.logger.error(f"log middleware error: {e}")
        return await handler(event, data)


async def log_errors(event):
    """Регистрируется как error-хендлер диспетчера: ловит все исключения.

    В aiogram 3.x error-хендлер получает ОДИН аргумент — ErrorEvent.
    Раньше сигнатура была (event, data) — отсюда TypeError:
    "log_errors() missing 1 required positional argument: 'data'".
    """
    logger = logging.getLogger('bot.hub')
    exception = getattr(event, 'exception', None) or event
    try:
        exc_text = getattr(exception, 'exc_info', None)
        if exc_text:
            logger.error(
                f"EXC в хендлере: {type(exception.exception).__name__}: {exception.exception}",
                exc_info=exception.exc_info,
            )
        else:
            logger.error(f"EXC в хендлере: {type(exception).__name__}: {exception}", exc_info=True)
    except Exception:
        try:
            logger.error(f"EXC в хендлере: {exception}", exc_info=True)
        except Exception:
            logger.error(f"EXC в хендлере: {exception}")
    return True


def setup_logging(dp, logger: logging.Logger):
    """Подключает логирование к диспетчеру (без блокировки обработки)."""
    dp.message.middleware.register(LoggingMiddleware(logger))
    dp.callback_query.middleware.register(LoggingMiddleware(logger))
    dp.inline_query.middleware.register(LoggingMiddleware(logger))
    dp.errors.register(log_errors)
    logger.info("🟢 Логирование действий включено (логирует ВСЕ сообщения/колбэки/ошибки)")