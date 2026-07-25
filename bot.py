import os, sys, asyncio, logging, threading, time
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from flask import Flask
from database.db import init_db, is_admin, add_admin
from handlers import router
from backup import GitHubBackup
import signal

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
shutdown_event = asyncio.Event()

@app.route('/')
@app.route('/healthz')
def health():
    return "OK", 200

def run_flask():
    try:
        port = int(os.getenv('PORT', 8080))
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"❌ Flask ошибка: {e}")

async def shutdown(signum=None, frame=None):
    logger.info("🛑 Получен SIGTERM, останавливаю бота...")
    await bot.delete_webhook()
    await dp.stop_polling()
    await bot.session.close()
    shutdown_event.set()
    logger.info("✅ Бот остановлен")

def handle_sigterm(signum, frame):
    asyncio.create_task(shutdown())

async def main():
    logger.info("🚀 Запуск...")
    
    # Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask запущен")
    
    # База данных
    init_db()
    logger.info("✅ База данных готова")
    
    # Восстановление бэкапа
    try:
        backup = GitHubBackup()
        backup.restore_latest_backup()
        logger.info("✅ Бекап восстановлен")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось восстановить бекап: {e}")
    
    init_db()
    logger.info("✅ Миграция БД выполнена")
    
    # Бэкап-цикл
    def backup_loop():
        while not shutdown_event.is_set():
            time.sleep(3600)
            try:
                GitHubBackup().backup_db()
                logger.info("✅ Бэкап создан")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка бэкапа: {e}")
    backup_thread = threading.Thread(target=backup_loop, daemon=True)
    backup_thread.start()
    
    # Админ
    admin_id = int(os.getenv("ADMIN_ID", 6957852385))
    if not is_admin(admin_id):
        add_admin(admin_id)
        logger.info(f"✅ Админ {admin_id} добавлен")
    
    # Регистрация команд
    dp.include_router(router)
    await bot.set_my_commands([
        types.BotCommand(command="start", description="🚀 Старт"),
        types.BotCommand(command="stats", description="📊 Статистика"),
        types.BotCommand(command="profile", description="👤 Профиль"),
        types.BotCommand(command="subscribe", description="💎 Premium"),
        types.BotCommand(command="referral", description="👥 Рефералы")
    ])
    
    # Удаляем вебхук
    await bot.delete_webhook(drop_pending_updates=True)
    
    logger.info("✅ Бот готов!")
    logger.info("🚀 Запуск polling...")
    
    # Обработка SIGTERM
    signal.signal(signal.SIGTERM, handle_sigterm)
    
    try:
        await dp.start_polling(bot, skip_updates=True)
    except asyncio.CancelledError:
        logger.info("⏹️ Polling отменён")
    finally:
        await bot.session.close()
        logger.info("✅ Сессия закрыта")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹️ Бот остановлен пользователем")
