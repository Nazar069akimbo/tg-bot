import os, sys, asyncio, logging, threading, time
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
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
    while True:
        await asyncio.sleep(30)
        try:
            with db_connection() as conn:
                cursor = conn.cursor()
                now_utc = datetime.now(timezone.utc).isoformat()
                cursor.execute("SELECT id, user_id, text FROM reminders WHERE sent = 0 AND time <= ?", (now_utc,))
                rows = cursor.fetchall()
                for row in rows:
                    try:
                        await bot.send_message(row['user_id'], f"⏰ Напоминание:\n{row['text']}")
                        cursor.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (row['id'],))
                        logger.info(f"✅ Напоминание {row['id']} отправлено {row['user_id']}")
                    except Exception as e:
                        logger.warning(f"⚠️ Напоминание {row['id']} не отправлено: {e}")
        except Exception as e:
            logger.error(f"❌ Ошибка воркера напоминаний: {e}")


async def subscription_worker():
    while True:
        await asyncio.sleep(86400)
        try:
            subs = get_expiring_subscriptions()
            for row in subs:
                user_id = row['user_id']
                if was_subscription_notified_today(user_id):
                    continue
                try:
                    until = datetime.fromisoformat(row['premium_until'])
                    days_left = (until - datetime.now()).days
                    plan_name = "Premium+" if row['plan'] == "premium_plus" else "Premium"
                    await bot.send_message(
                        user_id,
                        f"⚠️ Твоя подписка {plan_name} заканчивается через {days_left} дн.\n\n"
                        f"Продлить: /credits"
                    )
                    mark_subscription_notified(user_id)
                    logger.info(f"📩 Напоминание о подписке: {user_id}")
                except Exception as e:
                    logger.warning(f"⚠️ Не отправил {user_id}: {e}")
        except Exception as e:
            logger.error(f"❌ Ошибка воркера подписок: {e}")


async def main():
    logger.info("🚀 Запуск...")

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask запущен")

    # === ШАГ 1: Восстановить БД из GitHub (если нет локально) ===
    db_exists = os.path.exists('data/repsolver.db')
    if not db_exists:
        logger.info("📥 БД не найдена — восстанавливаю из GitHub...")
        try:
            GitHubBackup().restore_latest_backup()
            logger.info("✅ БД восстановлена из бэкапа")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось восстановить: {e}")

    init_db()
    migrate_db()
    logger.info("✅ База данных готова")

    # === ШАГ 2: Восстановить ПАПКИ ЮЗЕРОВ из GitHub ДО polling ===
    logger.info("📥 Восстанавливаю папки пользователей из GitHub...")
    try:
        ok = GitHubBackup().restore_users()
        if ok:
            logger.info("✅ Папки пользователей восстановлены из GitHub")
        else:
            logger.info("ℹ️ Папок пользователей на GitHub нет (или пусто)")
    except Exception as e:
        logger.warning(f"⚠️ Восстановление юзеров из GitHub: {e}")

    # === ШАГ 3: Восстановить токены из папок в БД ===
    try:
        count = restore_from_user_folders()
        if count > 0:
            logger.info(f"✅ Восстановлено из папок: {count} пользователей")
        else:
            logger.info("ℹ️ Из папок восстанавливать нечего")
    except Exception as e:
        logger.warning(f"⚠️ Восстановление из папок: {e}")

    # === ШАГ 4: Настройки моделей ===
    try:
        from handlers.helpers import load_settings_from_db
        load_settings_from_db()
        logger.info("✅ Настройки загружены из БД")
    except Exception as e:
        logger.warning(f"⚠️ Настройки: {e}")

    # === ШАГ 5: Фоновый бэкап БД раз в 30 мин ===
    def backup_loop():
        try:
            GitHubBackup().backup_db(reason='при старте')
            logger.info("✅ Бэкап БД при старте")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка первого бэкапа: {e}")

        while True:
            time.sleep(1800)
            try:
                GitHubBackup().backup_db(reason='по расписанию (30 мин)')
            except Exception as e:
                logger.warning(f"⚠️ Ошибка бэкапа БД: {e}")

    backup_thread = threading.Thread(target=backup_loop, daemon=True)
    backup_thread.start()
    logger.info("✅ Бэкап-воркер запущен (БД раз в 30 мин)")

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
        types.BotCommand(command="remind", description="⏰ Напоминание"),
        types.BotCommand(command="reminders", description="📋 Напоминания"),
        types.BotCommand(command="help", description="❓ Помощь"),
    ])

    asyncio.create_task(reminder_worker())
    logger.info("✅ Воркер напоминаний запущен")

    asyncio.create_task(subscription_worker())
    logger.info("✅ Воркер подписок запущен")

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("🚀 Бот готов! Пользователей в папках: " +
                str(sum(len(dirs) for _, dirs, _ in os.walk('data/users')) if os.path.exists('data/users') else 0))

    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹️ Бот остановлен")
