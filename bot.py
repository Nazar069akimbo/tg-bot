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
                          was_subscription_notified_today, restore_from_user_folders,
                          get_setting, check_tribute_transaction, add_tribute_transaction,
                          add_tokens)
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

@app.route('/tribute_webhook', methods=['POST'])
def tribute_webhook():
    import hmac
    import hashlib
    from flask import request, jsonify
    
    signature = request.headers.get('trbt-signature')
    api_key = os.getenv('TRIBUTE_API_KEY')
    
    if not signature or not api_key:
        logger.warning("⚠️ Вебхук без подписи или API-ключа")
        return jsonify({"error": "Unauthorized"}), 401
    
    expected = hmac.new(api_key.encode(), request.get_data(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        logger.warning("⚠️ Неверная подпись Tribute")
        return jsonify({"error": "Invalid signature"}), 401
    
    data = request.json
    if data.get('name') != 'new_digital_product':
        return jsonify({"status": "ignored"}), 200
    
    payload = data.get('payload', {})
    tx_id = payload.get('transaction_id') or payload.get('id')
    user_id = payload.get('telegram_user_id')
    product_name = payload.get('product_name', '')
    
    if not user_id or not tx_id:
        return jsonify({"status": "no user or tx"}), 200
    
    if check_tribute_transaction(tx_id):
        return jsonify({"status": "already processed"}), 200
        
    tokens_to_add = 0
    if "Старт" in product_name or "900" in product_name: tokens_to_add = 900
    elif "Базовый" in product_name or "1800" in product_name: tokens_to_add = 1800
    elif "Выгодный" in product_name or "2700" in product_name: tokens_to_add = 2700
    elif "Профи" in product_name or "3600" in product_name: tokens_to_add = 3600
    elif "Максимум" in product_name or "4500" in product_name: tokens_to_add = 4500
    else: return jsonify({"status": "unknown product"}), 200
    
    try:
        add_tokens(user_id, tokens_to_add)
        add_tribute_transaction(tx_id, user_id, product_name, tokens_to_add)
        logger.info(f"✅ Tribute: {user_id} оплатил {product_name}, начислено {tokens_to_add} токенов")
        
        import asyncio
        async def send_notify():
            try:
                await bot.send_message(
                    user_id, 
                    f"🎉 <b>Оплата прошла успешно!</b>\n\nВы купили: {product_name}\nНачислено: <b>+{tokens_to_add} токенов</b>\n\nПроверьте баланс: /balance"
                )
            except Exception as e:
                logger.warning(f"⚠️ Не удалось отправить уведомление {user_id}: {e}")
        
        loop = asyncio.get_event_loop()
        loop.create_task(send_notify())
    except Exception as e:
        logger.error(f"❌ Ошибка начисления: {e}")
        return jsonify({"error": "DB error"}), 500
    
    return jsonify({"status": "ok"}), 200

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
            now = datetime.now()
            in_3_days = (now + timedelta(days=3)).isoformat()
            
            with db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT user_id, plan, premium_until FROM users WHERE plan IN ('premium', 'premium_plus') AND premium_until > ? AND premium_until <= ?", (now.isoformat(), in_3_days))
                
                for row in cursor.fetchall():
                    user_id = row['user_id']
                    until = datetime.fromisoformat(row['premium_until'])
                    days_left = (until - now).days
                    plan_name = "Premium+" if row['plan'] == "premium_plus" else "Premium"
                    
                    text = f"⚠️ <b>Подписка {plan_name} заканчивается!</b>\n\nОсталось дней: <b>{days_left}</b>\nНе забудь продлить, чтобы сохранить скидку и отсутствие водяных знаков!\n\nПродлить: /credits"
                    try:
                        await bot.send_message(user_id, text)
                    except Exception as e:
                        logger.warning(f"⚠️ Не отправил {user_id}: {e}")
        except Exception as e:
            logger.error(f"❌ Ошибка воркера подписок: {e}")
        await asyncio.sleep(86400)

def smart_backup_worker():
    logger.info("✅ Умный воркер бэкапов запущен")
    last_db_time = 0
    last_users_time = 0
    last_daily_date = None
    
    while True:
        try:
            now = datetime.now()
            current_time = time.time()
            
            db_freq = int(get_setting("backup_db_freq") or "0")
            users_freq = int(get_setting("backup_users_freq") or "0")
            daily_time_str = get_setting("backup_time") or "05:00"
            
            if db_freq > 0 and (current_time - last_db_time) >= (db_freq * 60):
                logger.info(f"⏳ Авто-бэкап БД")
                GitHubBackup().backup_db(reason='по расписанию')
                last_db_time = current_time
                
            if users_freq > 0 and (current_time - last_users_time) >= (users_freq * 60):
                logger.info(f"⏳ Авто-бэкап юзеров")
                GitHubBackup().backup_users(reason='по расписанию')
                last_users_time = current_time
                
            try:
                target_h, target_m = map(int, daily_time_str.split(":"))
                if now.hour == target_h and now.minute == target_m and last_daily_date != now.date():
                    logger.info(f"⏳ Ежедневный бэкап ({daily_time_str})")
                    GitHubBackup().backup_all(reason='ежедневный')
                    last_daily_date = now.date()
            except ValueError: pass
                
            time.sleep(30)
        except Exception as e:
            logger.error(f"❌ Ошибка умного воркера: {e}")
            time.sleep(30)

async def main():
    logger.info("🚀 Запуск...")
    threading.Thread(target=run_flask, daemon=True).start()

    if not os.path.exists('data/repsolver.db'):
        try: GitHubBackup().restore_latest_backup()
        except Exception as e: logger.warning(f"⚠️ Не удалось восстановить БД: {e}")

    init_db()
    migrate_db()
    logger.info("✅ База данных готова")

    if not os.path.exists('data/users') or len(os.listdir('data/users')) == 0:
        try: GitHubBackup().restore_users(skip_images=True)
        except Exception as e: logger.warning(f"⚠️ Не удалось восстановить папки: {e}")
    else:
        logger.info("⏭ Папки юзеров уже на месте")

    try: restore_from_user_folders()
    except Exception: pass

    threading.Thread(target=smart_backup_worker, daemon=True).start()

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
