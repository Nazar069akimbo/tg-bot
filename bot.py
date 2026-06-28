import os, sys, asyncio, logging, threading, time
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from flask import Flask
from database.db import init_db, is_admin, add_admin
from handlers import router
from backup import GitHubBackup

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не найден!")
    sys.exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = Flask(__name__)

@app.route('/')
@app.route('/healthz')
def health():
    return "OK", 200

def run_flask():
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)))

async def main():
    logger.info("🚀 Запуск...")
    init_db()
    
    threading.Thread(target=run_flask, daemon=True).start()
    
    backup = GitHubBackup()
    backup.restore_latest_backup()
    
    def backup_loop():
        while True:
            time.sleep(3600)
            try:
                GitHubBackup().backup_db()
            except Exception as e:
                logger.error(f"❌ Бэкап: {e}")
    threading.Thread(target=backup_loop, daemon=True).start()
    
    if not is_admin(int(os.getenv("ADMIN_ID", 6957852385))):
        add_admin(int(os.getenv("ADMIN_ID", 6957852385)))
    
    dp.include_router(router)
    
    # ИСПРАВЛЕНО: правильный синтаксис BotCommand
    await bot.set_my_commands([
        types.BotCommand(command="start", description="🚀 Старт"),
        types.BotCommand(command="stats", description="📊 Статистика"),
        types.BotCommand(command="profile", description="👤 Профиль"),
        types.BotCommand(command="subscribe", description="💎 Premium"),
        types.BotCommand(command="referral", description="👥 Рефералы")
    ])
    
    logger.info("✅ Бот готов!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
