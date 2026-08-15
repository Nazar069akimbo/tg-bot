import os, sys, asyncio, logging, threading, time
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from flask import Flask
from database.db import init_db, migrate_db, is_admin, add_admin
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
ADMIN_ID = int(os.getenv('ADMIN_ID', 6957852385))

@app.route('/')
@app.route('/healthz')
def health():
    return "OK", 200

def run_flask():
    port = int(os.getenv('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

async def main():
    logger.info("🚀 Запуск...")
    
    # Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask запущен")
    
    # База данных
    init_db()
    migrate_db()
    logger.info("✅ База данных готова")
    
    # Бэкап-цикл
    def backup_loop():
        while True:
            time.sleep(3600)
            try:
                GitHubBackup().backup_db()
                logger.info("✅ Бэкап создан")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка бэкапа: {e}")
    backup_thread = threading.Thread(target=backup_loop, daemon=True)
    backup_thread.start()
    
    # Добавляем админа
    if not is_admin(ADMIN_ID):
        add_admin(ADMIN_ID)
        logger.info(f"✅ Админ {ADMIN_ID} добавлен")
    
    # Регистрируем роутер
    dp.include_router(router)
    
    # Команды
    await bot.set_my_commands([
        types.BotCommand(command="start", description="🚀 Старт"),
        types.BotCommand(command="balance", description="💰 Баланс"),
        types.BotCommand(command="profile", description="👤 Профиль"),
        types.BotCommand(command="help", description="❓ Помощь")
    ])
    
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Вебхук удалён")
    logger.info("🚀 Бот готов!")
    
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹️ Бот остановлен")
