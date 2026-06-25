import os
import sys
import asyncio
import logging
import threading
import time
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.fsm.storage.memory import MemoryStorage
from threading import Thread
from flask import Flask

app = Flask(__name__)

@app.route('/')
@app.route('/healthz')
def health():
    return "OK", 200

def run_flask():
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)))

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.db import init_db, init_settings, is_admin, add_admin
from handlers import (
    start_handler, stats_handler, profile_handler, 
    settings_handler, subscribe_handler, referral_handler, 
    solve_handler, admin_handler, leaderboard_handler, help_handler,
    contact_handler
)
from middleware import AuthMiddleware
from backup_github import GitHubBackup

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
    
    # Сначала удаляем webhook и все pending updates
    logger.info("🗑️ Удаляю webhook...")
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Webhook удалён")
    
    # Ждём чтобы Telegram точно обработал
    await asyncio.sleep(2)
    
    thread = Thread(target=run_flask)
    thread.daemon = True
    thread.start()
    logger.info("✅ Flask сервер запущен")
    
    init_db()
    init_settings()
    
    backup = GitHubBackup()
    backup.restore_latest_backup()
    
    def backup_loop():
        while True:
            time.sleep(3600)
            try:
                backup.backup_db(reason='каждый час')
            except Exception as e:
                logger.error(f"❌ Ошибка бэкапа: {e}")
    
    backup_thread = threading.Thread(target=backup_loop, daemon=True)
    backup_thread.start()
    logger.info("✅ Запущен планировщик бэкапов (каждый час)")
    
    if not is_admin(ADMIN_ID):
        add_admin(ADMIN_ID)
    
    await set_commands()
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    
    dp.include_router(admin_handler.router)
    dp.include_router(start_handler.router)
    dp.include_router(stats_handler.router)
    dp.include_router(profile_handler.router)
    dp.include_router(settings_handler.router)
    dp.include_router(subscribe_handler.router)
    dp.include_router(referral_handler.router)
    dp.include_router(leaderboard_handler.router)
    dp.include_router(help_handler.router)
    dp.include_router(contact_handler.router)
    dp.include_router(solve_handler.router)
    
    logger.info("📡 Запуск POLLING...")
    logger.info("✅ Бот готов!")
    
    # Бесконечный цикл с авто-восстановлением
    while True:
        try:
            await dp.start_polling(bot, skip_updates=True, timeout=30)
        except Exception as e:
            logger.error(f"❌ Polling error: {e}")
            logger.info("🔄 Перезапуск polling через 3 секунды...")
            await asyncio.sleep(3)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен")
