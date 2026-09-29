import os, sys, asyncio, logging, threading, time
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from flask import Flask
from database.db import init_db, migrate_db, is_admin, add_admin, db_connection
from handlers import routers
from handlers.logging_hub import setup_logging
from backup import GitHubBackup
from datetime import datetime

load_dotenv()

# ═══════════ ЛОГИРОВАНИЕ ═══════════
os.makedirs('logs', exist_ok=True)
LOG_FORMAT = '%(asctime)s | %(levelname)-7s | %(name)s | %(message)s'

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler('logs/bot.log', maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8'),
    ]
)
logging.getLogger('aiogram').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не найден!")
    sys.exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = Flask(__name__)
ADMIN_ID = int(os.getenv('ADMIN_ID', 6957852385))

setup_logging(dp, logger)


@app.route('/')
@app.route('/healthz')
def health():
    return "OK", 200


def run_flask():
    port = int(os.getenv('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)


async def reminder_worker():
    """Фоновый воркер: отправляет наступившие напоминания."""
    while True:
        await asyncio.sleep(30)
        try:
            with db_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                cursor.execute("SELECT id, user_id, text FROM reminders WHERE sent = 0 AND time <= ?", (now,))
                rows = cursor.fetchall()
                for row in rows:
                    try:
                        await bot.send_message(row['user_id'], f"⏰ **Напоминание:**\n{row['text']}")
                        cursor.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (row['id'],))
                        logger.info(f"✅ Напоминание {row['id']} отправлено {row['user_id']}")
                    except Exception as e:
                        logger.warning(f"⚠️ Напоминание {row['id']} не отправлено: {e}")
        except Exception as e:
            logger.error(f"❌ Ошибка воркера напоминаний: {e}")


async def main():
    logger.info("🚀 Запуск...")

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask запущен")

    init_db()
    migrate_db()
    logger.info("✅ База данных готова")

    def backup_loop():
        while True:
            time.sleep(3600)
            try:
                GitHubBackup().backup_all(reason='по расписанию (1 час)')
            except Exception as e:
                logger.warning(f"⚠️ Ошибка бэкапа: {e}")

    backup_thread = threading.Thread(target=backup_loop, daemon=True)
    backup_thread.start()
    logger.info("✅ Бэкап-воркер запущен")

    if not is_admin(ADMIN_ID):
        add_admin(ADMIN_ID)
        logger.info(f"✅ Админ {ADMIN_ID} добавлен")

    for router in routers:
        dp.include_router(router)
        logger.info(f"✅ Роутер: {router}")

    await bot.set_my_commands([
        types.BotCommand(command="start", description="🚀 Старт"),
        types.BotCommand(command="balance", description="💰 Баланс"),
        types.BotCommand(command="profile", description="👤 Профиль"),
        types.BotCommand(command="prices", description="💰 Цены"),
        types.BotCommand(command="credits", description="🛒 Купить токены"),
        types.BotCommand(command="memory", description="🧠 Моя память"),
        types.BotCommand(command="remind", description="⏰ Напоминание"),
        types.BotCommand(command="reminders", description="📋 Напоминания"),
        types.BotCommand(command="help", description="❓ Помощь"),
    ])

    asyncio.create_task(reminder_worker())
    logger.info("✅ Воркер напоминаний запущен")

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("🚀 Бот готов!")

    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹️ Бот остановлен")
