import os, sys, asyncio, logging, threading, time
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from flask import Flask
from database.db import init_db, migrate_db, is_admin, add_admin
from database.db import get_due_reminders, mark_reminder_sent, reset_daily_reminders
from handlers import routers
from handlers.logging_hub import setup_logging
from backup import GitHubBackup

load_dotenv()

# ═══════════ ЛОГИРОВАНИЕ: консоль + файл logs/bot.log (ротация 5МБ x 3) ═══════════
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
logging.getLogger('aiogram').setLevel(logging.WARNING)  # меньше шума от aiogram
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не найден!")
    sys.exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = Flask(__name__)
ADMIN_ID = int(os.getenv('ADMIN_ID', 6957852385))

# Подключаем логирование ВСЕХ действий пользователей (в файл logs/bot.log)
setup_logging(dp, logger)

@app.route('/')
@app.route('/healthz')
def health():
    return "OK", 200

def run_flask():
    port = int(os.getenv('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

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
                GitHubBackup().backup_db()
                logger.info("✅ Бэкап создан")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка бэкапа: {e}")
    backup_thread = threading.Thread(target=backup_loop, daemon=True)
    backup_thread.start()
    
    if not is_admin(ADMIN_ID):
        add_admin(ADMIN_ID)
        logger.info(f"✅ Админ {ADMIN_ID} добавлен")

    # === ФОНОВЫЙ ВОРКЕР НАПОМИНАНИЙ ===
    async def reminder_worker():
        logger.info("⏰ Воркер напоминаний запущен")
        while True:
            await asyncio.sleep(30)
            try:
                now = datetime.now()
                now_iso = now.isoformat()
                due = get_due_reminders(now_iso)
                for r in due:
                    try:
                        await bot.send_message(
                            r["user_id"],
                            f"⏰ <b>Напоминание:</b>\n{r['text']}",
                            parse_mode="HTML"
                        )
                        mark_reminder_sent(r["id"])
                        logger.info(f"⏰ [{r['user_id']}] Напоминание отправлено: {r['text'][:50]}")
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось отправить напоминание {r['id']}: {e}")
                # Повторяющиеся напоминания (*) — сбрасываем на следующий день
                reset_daily_reminders(now_iso)
            except Exception as e:
                logger.error(f"❌ Ошибка воркера напоминаний: {e}")
    asyncio.create_task(reminder_worker())
    
    # === РЕГИСТРИРУЕМ РОУТЕРЫ ===
    for router in routers:
        dp.include_router(router)
        logger.info(f"✅ Роутер зарегистрирован: {router}")
    
    await bot.set_my_commands([
        types.BotCommand(command="start", description="🚀 Старт"),
        types.BotCommand(command="balance", description="💰 Баланс"),
        types.BotCommand(command="profile", description="👤 Профиль"),
        types.BotCommand(command="help", description="❓ Помощь"),
        types.BotCommand(command="search", description="🔍 Поиск"),
        types.BotCommand(command="prices", description="💰 Цены"),
        types.BotCommand(command="credits", description="🛒 Купить токены"),
        types.BotCommand(command="remind", description="⏰ Напоминание"),
        types.BotCommand(command="reminders", description="📋 Список напоминаний"),
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
