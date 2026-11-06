import os, sys, asyncio, logging, threading, time
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone, timedelta
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
    logger.error("❌ BOT_TOKEN не найден!")
    sys.exit(1)

_admin_raw = os.getenv('ADMIN_ID')
if not _admin_raw:
    logger.error("❌ ADMIN_ID не задан")
    sys.exit(1)
ADMIN_ID = int(_admin_raw)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
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
                rows = cursor.fetchall()
                for row in rows:
                    try:
                        await bot.send_message(row['user_id'], f"⏰ <b>Напоминание:</b>\n{row['text']}")
                        cursor.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (row['id'],))
                    except Exception as e:
                        logger.warning(f"⚠️ Напоминание {row['id']} не отправлено: {e}")
        except Exception as e:
            logger.error(f"❌ Ошибка воркера напоминаний: {e}")


async def subscription_worker():
    while True:
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
                        f"⚠️ Твоя подписка <b>{plan_name}</b> заканчивается через <b>{days_left}</b> дн.\n\n"
                        f"Продлить: /credits"
                    )
                    mark_subscription_notified(user_id)
                except Exception as e:
                    logger.warning(f"⚠️ Не отправил {user_id}: {e}")
        except Exception as e:
            logger.error(f"❌ Ошибка воркера подписок: {e}")
        await asyncio.sleep(86400)


async def main():
    logger.info("🚀 Запуск...")

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # 1. Восстановление БД (если файла нет)
    db_exists = os.path.exists('data/repsolver.db')
    if not db_exists:
        logger.info("📥 БД не найдена — восстанавливаю из GitHub...")
        try:
            GitHubBackup().restore_latest_backup()
        except Exception as e:
            logger.warning(f"⚠️ Не удалось восстановить БД: {e}")

    init_db()
    migrate_db()
    logger.info("✅ База данных готова")

    # 2. Восстановление папок юзеров (ТОЛЬКО если их нет локально)
    if not os.path.exists('data/users') or len(os.listdir('data/users')) == 0:
        logger.info("📥 Папки юзеров пусты — восстанавливаю из GitHub...")
        try:
            GitHubBackup().restore_users(skip_images=True)
        except Exception as e:
            logger.warning(f"⚠️ Не удалось восстановить папки: {e}")
    else:
        logger.info("⏭ Папки юзеров уже на месте — пропускаю скачивание (экономия трафика)")

    # 3. Восстановление токенов из папок в БД
    try:
        count = restore_from_user_folders()
        if count > 0:
            logger.info(f"✅ Восстановлено из папок: {count} пользователей")
    except Exception as e:
        logger.warning(f"⚠️ Восстановление из папок: {e}")

    # 4. Бэкап БД раз в 15 минут (вместо 30)
    def backup_loop():
        try:
            GitHubBackup().backup_db(reason='при старте')
        except Exception as e:
            logger.warning(f"⚠️ Ошибка первого бэкапа: {e}")

        while True:
            time.sleep(900) # 15 минут
            try:
                GitHubBackup().backup_db(reason='по расписанию')
            except Exception as e:
                logger.warning(f"⚠️ Ошибка бэкапа БД: {e}")

    backup_thread = threading.Thread(target=backup_loop, daemon=True)
    backup_thread.start()
    logger.info("✅ Бэкап-воркер запущен (БД раз в 15 мин)")

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
        types.BotCommand(command="remind", description="⏰ Напоминание"),
        types.BotCommand(command="reminders", description="📋 Напоминания"),
        types.BotCommand(command="bonus", description="🎁 Ежедневный бонус"),
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
        logger.info("⏹️ Бот остановлен")
