import os, sys, asyncio, logging, threading, time
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from flask import Flask
from database.db import (init_db, migrate_db, is_admin, add_admin, db_connection,
                          get_expiring_subscriptions, mark_subscription_notified,
                          was_subscription_notified_today, restore_from_user_folders)
from handlers import routers
from handlers.logging_hub import setup_logging
from backup import GitHubBackup

load_dotenv()

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
    sys.exit(1)

_admin_raw = os.getenv('ADMIN_ID')
if not _admin_raw:
    sys.exit(1)
ADMIN_ID = int(_admin_raw)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
app = Flask(__name__)
setup_logging(dp, logger)

@app.route('/')
@app.route('/healthz')
def health():
    return "OK", 200

def run_flask():
    port = int(os.getenv('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

async def reminder_worker():
    while True:
        await asyncio.sleep(30)
        try:
            with db_connection() as conn:
                cursor = conn.cursor()
                now_utc = datetime.now(timezone.utc).isoformat()
                cursor.execute("SELECT id, user_id, text FROM reminders WHERE sent = 0 AND time <= ?", (now_utc,))
                for row in cursor.fetchall():
                    try:
                        await bot.send_message(row['user_id'], f"⏰ <b>Напоминание:</b>\n{row['text']}")
                        cursor.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (row['id'],))
                    except: pass
        except Exception as e:
            logger.error(f"❌ Ошибка воркера напоминаний: {e}")

async def subscription_worker():
    while True:
        try:
            subs = get_expiring_subscriptions()
            for row in subs:
                user_id = row['user_id']
                if was_subscription_notified_today(user_id): continue
                try:
                    until = datetime.fromisoformat(row['premium_until'])
                    days_left = (until - datetime.now()).days
                    plan_name = "Premium+" if row['plan'] == "premium_plus" else "Premium"
                    await bot.send_message(user_id, f"⚠️ Твоя подписка <b>{plan_name}</b> заканчивается через <b>{days_left}</b> дн.\n\nПродлить: /credits")
                    mark_subscription_notified(user_id)
                except: pass
        except Exception as e:
            logger.error(f"❌ Ошибка воркера подписок: {e}")
        await asyncio.sleep(86400)

# === ВОРКЕР ЕЖЕДНЕВНОГО БЭКАПА (СТРОГО В 05:00) ===
def daily_backup_worker():
    logger.info("✅ Воркер ежедневного бэкапа запущен (строго в 05:00)")
    last_backup_date = None
    
    while True:
        try:
            now = datetime.now()
            if now.hour == 5 and last_backup_date != now.date():
                logger.info("⏳ Запуск ежедневного бэкапа в 05:00...")
                GitHubBackup().backup_all(reason='ежедневный (05:00)')
                last_backup_date = now.date()
                logger.info("✅ Ежедневный бэкап завершен!")
            
            time.sleep(60) # Проверяем каждую минуту
        except Exception as e:
            logger.error(f"❌ Ошибка воркера бэкапа: {e}")
            time.sleep(60)

async def main():
    logger.info("🚀 Запуск...")
    threading.Thread(target=run_flask, daemon=True).start()

    if not os.path.exists('data/repsolver.db'):
        try:
            GitHubBackup().restore_latest_backup()
        except Exception as e:
            logger.warning(f"⚠️ Не удалось восстановить БД: {e}")

    init_db()
    migrate_db()
    logger.info("✅ База данных готова")

    # Скачиваем папки юзеров ТОЛЬКО если их нет
    if not os.path.exists('data/users') or len(os.listdir('data/users')) == 0:
        try:
            GitHubBackup().restore_users(skip_images=True)
        except Exception as e:
            logger.warning(f"⚠️ Не удалось восстановить папки: {e}")
    else:
        logger.info("⏭ Папки юзеров уже на месте")

    try:
        restore_from_user_folders()
    except Exception: pass

    # Запускаем поток ежедневного бэкапа
    threading.Thread(target=daily_backup_worker, daemon=True).start()

    if not is_admin(ADMIN_ID):
        add_admin(ADMIN_ID)

    for router in routers:
        dp.include_router(router)

    await bot.set_my_commands([
        types.BotCommand(command="start", description="🚀 Старт"),
        types.BotCommand(command="balance", description="💰 Баланс"),
        types.BotCommand(command="profile", description="👤 Профиль"),
        types.BotCommand(command="prices", description="💰 Цены"),
        types.BotCommand(command="credits", description="🛒 Купить токены"),
        types.BotCommand(command="help", description="❓ Помощь"),
    ])

    asyncio.create_task(reminder_worker())
    asyncio.create_task(subscription_worker())

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("🚀 Бот готов!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
