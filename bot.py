import os
import sys
import asyncio
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.fsm.storage.memory import MemoryStorage

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.db import init_db, init_settings, is_admin, add_admin
from handlers import (
    start_handler, stats_handler, profile_handler, 
    settings_handler, subscribe_handler, referral_handler, 
    solve_handler, admin_handler, leaderboard_handler, help_handler
)
from middleware import AuthMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не найден в .env файле!")
    sys.exit(1)

ADMIN_ID = int(os.getenv("ADMIN_ID", 6957852385))

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

async def set_commands():
    """Установка команд бота (только основные)"""
    try:
        commands = [
            BotCommand(command="start", description="🚀 Запустить бота"),
            BotCommand(command="stats", description="📊 Статистика"),
            BotCommand(command="profile", description="👤 Профиль"),
            BotCommand(command="settings", description="⚙️ Настройки"),
            BotCommand(command="subscribe", description="💎 Premium"),
            BotCommand(command="referral", description="👥 Рефералы"),
            # Убираем leaderboard, help, admin из списка команд
            # BotCommand(command="leaderboard", description="🏆 Рейтинг"),
            # BotCommand(command="admin", description="🛡️ Админ-панель"),
            # BotCommand(command="help", description="❓ Помощь"),
        ]
        await bot.set_my_commands(commands)
        logger.info("✅ Команды установлены")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось установить команды: {e}")

async def main():
    """Главная функция"""
    try:
        logger.info("🚀 Запуск бота...")
        
        # Инициализация базы данных
        init_db()
        init_settings()
        
        # Добавление администратора
        if not is_admin(ADMIN_ID):
            add_admin(ADMIN_ID)
            logger.info(f"✅ Администратор {ADMIN_ID} добавлен")
        
        # Установка команд
        await set_commands()
        
        # Подключение middleware
        dp.message.middleware(AuthMiddleware())
        dp.callback_query.middleware(AuthMiddleware())
        
        # Подключение роутеров
        dp.include_router(start_handler.router)
        dp.include_router(stats_handler.router)
        dp.include_router(profile_handler.router)
        dp.include_router(settings_handler.router)
        dp.include_router(subscribe_handler.router)
        dp.include_router(referral_handler.router)
        dp.include_router(solve_handler.router)
        dp.include_router(admin_handler.router)
        dp.include_router(leaderboard_handler.router)
        dp.include_router(help_handler.router)
        
        logger.info("✅ Все модули загружены!")
        logger.info("✅ Бот готов к работе!")
        logger.info("🔄 Начинаем поллинг...")
        
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
