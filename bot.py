import os
import sys
import asyncio
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.fsm.storage.memory import MemoryStorage
from threading import Thread
from flask import Flask

# ========== FLASK ДЛЯ HEALTHCHECK ==========
app = Flask(__name__)

@app.route('/')
@app.route('/healthz')
def health():
    return "OK", 200

def run_flask():
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)))

# ========== ОСНОВНОЙ КОД БОТА ==========
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
    logger.error("❌ BOT_TOKEN не найден!")
    sys.exit(1)

ADMIN_ID = int(os.getenv("ADMIN_ID", 6957852385))

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

async def set_commands():
    commands = [
        BotCommand(command="start", description="🚀 Запустить бота"),
        BotCommand(command="stats", description="📊 Статистика"),
        BotCommand(command="profile", description="👤 Профиль"),
        BotCommand(command="settings", description="⚙️ Настройки"),
        BotCommand(command="subscribe", description="💎 Premium"),
        BotCommand(command="referral", description="👥 Рефералы"),
    ]
    await bot.set_my_commands(commands)

async def main():
    logger.info("🚀 Запуск бота...")
    
    # Запускаем Flask в отдельном потоке
    thread = Thread(target=run_flask)
    thread.daemon = True
    thread.start()
    logger.info("✅ Flask сервер запущен на порту 8080")
    
    init_db()
    init_settings()
    if not is_admin(ADMIN_ID):
        add_admin(ADMIN_ID)
    
    await set_commands()
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    
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
    
    logger.info("✅ Бот готов!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен")
