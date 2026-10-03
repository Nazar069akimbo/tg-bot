import sqlite3
import os
import json
import secrets
import threading
import queue
from datetime import datetime, timedelta
from contextlib import contextmanager

DB_PATH = 'data/repsolver.db'
os.makedirs('data', exist_ok=True)

TIMEZONE_OFFSET = int(os.getenv("TIMEZONE_OFFSET", "3"))
DAILY_LIMITS = {"basic": 30, "premium": 100, "premium_plus": 300}
DAILY_TEXT_LIMITS = {"basic": 10, "premium": 10, "premium_plus": 10}
DAILY_IMAGE_LIMITS = {"basic": 2, "premium": 2, "premium_plus": 2}

_db_queue = queue.Queue()
_db_thread = None
_db_running = True

_db_backup_timer = None
_db_backup_lock = threading.Lock()


def _db_worker():
    conn = None
    while _db_running:
        try:
            task = _db_queue.get(timeout=1)
            if task is None:
                continue
            func, args, kwargs, result_queue, error_queue = task
            try:
                if conn is None:
                    conn = sqlite3.connect(DB_PATH, timeout=30)
                    conn.row_factory = sqlite3.Row
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA synchronous=NORMAL")
                cursor = conn.cursor()
                result = func(conn, cursor, *args, **kwargs)
                conn.commit()
                if result_queue:
                    result_queue.put(result)
            except Exception as e:
                if conn:
                    conn.rollback()
                if error_queue:
                    error_queue.put(e)
                else:
                    print(f"❌ Ошибка БД: {e}")
            finally:
                _db_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            print(f"❌ Ошибка воркера БД: {e}")
            conn = None


def _ensure_db_thread():
    global _db_thread
    if _db_thread is None or not _db_thread.is_alive():
        _db_thread = threading.Thread(target=_db_worker, daemon=True)
        _db_thread.start()
        print("✅ Поток БД запущен")


def _execute_db(func, *args, **kwargs):
    _ensure_db_thread()
    result_queue = queue.Queue()
    error_queue = queue.Queue()
    _db_queue.put((func, args, kwargs, result_queue, error_queue))
    try:
        if not error_queue.empty():
            raise error_queue.get(timeout=1)
        return result_queue.get(timeout=30)
    except queue.Empty:
        raise TimeoutError("Запрос к БД не выполнен за 30 секунд")
    except Exception as e:
        raise e


def db_operation(func):
    def wrapper(*args, **kwargs):
        return _execute_db(func, *args, **kwargs)
    return wrapper


def reload_db_connection():
    global _db_running, _db_thread, _db_queue
    _db_running = False
    if _db_thread:
        _db_thread.join(timeout=2)
    _db_running = True
    _db_thread = None
    _db_queue = queue.Queue()
    _ensure_db_thread()
    print("🔄 Поток БД перезапущен")


def _schedule_db_backup():
    global _db_backup_timer
    with _db_backup_lock:
        if _db_backup_timer is not None:
            _db_backup_timer.cancel()
        _db_backup_timer = threading.Timer(10, _do_db_backup)
        _db_backup_timer.daemon = True
        _db_backup_timer.start()


def _do_db_backup():
    global _db_backup_timer
    try:
        from backup import GitHubBackup
        GitHubBackup().backup_db(reason='изменение')
    except Exception as e:
        print(f"⚠️ Бэкап БД: {e}")
    with _db_backup_lock:
        _db_backup_timer = None


@contextmanager
def db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            joined TEXT,
            tokens INTEGER DEFAULT 0,
            trial_start TEXT,
            trial_active INTEGER DEFAULT 0,
            is_blocked INTEGER DEFAULT 0,
            plan TEXT DEFAULT "basic",
            premium_until TEXT,
            daily_requests INTEGER DEFAULT 30,
            daily_requests_used INTEGER DEFAULT 0,
            daily_images_used INTEGER DEFAULT 0,
            week_images_used INTEGER DEFAULT 0,
            week_start TEXT,
            daily_reset TEXT,
            paid_premium INTEGER DEFAULT 0
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_memory (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            context_history TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS images_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            prompt TEXT,
            enhanced_prompt TEXT,
            model TEXT,
            image_data TEXT,
            session_id TEXT,
            created_at TEXT
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER,
            joined TEXT,
            UNIQUE(referrer_id, referred_id)
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            added_at TEXT
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            stars_amount INTEGER,
            telegram_payload TEXT,
            status TEXT,
            timestamp TEXT,
            plan TEXT
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages_to_admin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            text TEXT,
            date TEXT,
            status TEXT DEFAULT "new"
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS promocodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            bonus_tokens INTEGER DEFAULT 0,
            max_uses INTEGER DEFAULT 1,
            used INTEGER DEFAULT 0,
            created_at TEXT,
            expires_at TEXT
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS promocode_uses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            promocode_id INTEGER,
            user_id INTEGER,
            used_at TEXT
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            text TEXT,
            time TEXT,
            sent INTEGER DEFAULT 0,
            created_at TEXT
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS model_settings (
            task TEXT PRIMARY KEY,
            model TEXT,
            updated_at TEXT
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS tariffs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            price_rub INTEGER DEFAULT 0,
            stars INTEGER DEFAULT 0,
            tokens INTEGER DEFAULT 0,
            days INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscription_notifications (
            user_id INTEGER PRIMARY KEY,
            last_notified TEXT
        )
        ''')

        default_settings = [
            ('free_input_chars', '500'),
            ('free_output_words', '50'),
            ('premium_input_chars', '3000'),
            ('premium_output_words', '300'),
        ]
        for key, value in default_settings:
            cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))

        default_models = [
            ('text_chat', 'gpt-4.1-nano'),
            ('image_generate', 'flux-schnell'),
            ('prompt_enhance', 'gpt-4.1-nano'),
        ]
        for task, model in default_models:
            cursor.execute("INSERT OR IGNORE INTO model_settings (task, model, updated_at) VALUES (?, ?, ?)",
                           (task, model, datetime.now().isoformat()))

        cursor.execute("SELECT COUNT(*) FROM tariffs")
        if cursor.fetchone()[0] == 0:
            defaults = [
                ('tokens', 'Старт', 100, 50, 900, 0, 1),
                ('tokens', 'Базовый', 200, 100, 1800, 0, 2),
                ('tokens', 'Выгодный', 300, 150, 2700, 0, 3),
                ('tokens', 'Профи', 400, 200, 3600, 0, 4),
                ('tokens', 'Максимум', 500, 250, 4500, 0, 5),
                ('premium', 'Premium', 300, 150, 3000, 30, 1),
                ('premium', 'Premium+', 600, 300, 8000, 30, 2),
            ]
            for kind, name, price_rub, stars, tokens, days, order in defaults:
                cursor.execute(
                    "INSERT INTO tariffs (kind, name, price_rub, stars, tokens, days, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (kind, name, price_rub, stars, tokens, days, order)
                )

        ADMIN_ID = int(os.getenv('ADMIN_ID', 6957852385))
        cursor.execute("INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)",
                       (ADMIN_ID, datetime.now().isoformat()))

        print("✅ База данных инициализирована")


def migrate_db():
    with db_connection() as conn:
        cursor = conn.cursor()
        for col, typ, default in [
            ("daily_requests", "INTEGER", "30"),
            ("daily_requests_used", "INTEGER", "0"),
            ("daily_images_used", "INTEGER", "0"),
            ("week_images_used", "INTEGER", "0"),
            ("week_start", "TEXT", None),
            ("daily_reset", "TEXT", None),
        ]:
            try:
                if default:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {typ} DEFAULT {default}")
                else:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")
            except Exception:
                pass
        print("✅ БД в порядке")


# ===== ПОЛЬЗОВАТЕЛИ =====
@db_operation
def get_user(conn, cursor, user_id):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return cursor.fetchone()


@db_operation
def create_user(conn, cursor, user_id, username):
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        return True
    now = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO users (user_id, username, joined, trial_start, trial_active, daily_reset)
        VALUES (?, ?, ?, ?, 0, ?)
    """, (user_id, username, now, now, now))
    return True


def force_create_user(user_id, username=None):
    try:
        user = get_user(user_id)
        if user:
            return user
        create_user(user_id, username or str(user_id))
        return get_user(user_id)
    except Exception:
        return None


@db_operation
def get_tokens(conn, cursor, user_id):
    cursor.execute("SELECT tokens FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else 0


@db_operation
def add_tokens(conn, cursor, user_id, amount):
    cursor.execute("UPDATE users SET tokens = tokens + ? WHERE user_id = ?", (amount, user_id))
    _schedule_db_backup()
    try:
        from utils.user_storage import save_user_tokens
        cursor.execute("SELECT tokens, plan, premium_until FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            save_user_tokens(user_id, row[0], row[1], row[2])
    except Exception as e:
        print(f"⚠️ save_user_tokens: {e}")


@db_operation
def spend_tokens(conn, cursor, user_id, amount):
    cursor.execute("SELECT tokens FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row and row[0] >= amount:
        cursor.execute("UPDATE users SET tokens = tokens - ? WHERE user_id = ?", (amount, user_id))
        _schedule_db_backup()
        try:
            from utils.user_storage import save_user_tokens
            cursor.execute("SELECT tokens, plan, premium_until FROM users WHERE user_id = ?", (user_id,))
            row2 = cursor.fetchone()
            if row2:
                save_user_tokens(user_id, row2[0], row2[1], row2[2])
        except Exception as e:
            print(f"⚠️ save_user_tokens: {e}")
        return True
    return False


# ===== ЛИМИТЫ =====
@db_operation
def get_text_tokens_today(conn, cursor, user_id):
    cursor.execute("SELECT plan, daily_requests_used, daily_reset, tokens FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        return 0, 10
    plan = row[0] or "basic"
    used = row[1] or 0
    last_reset = row[2]
    balance = row[3] or 0
    if balance > 0:
        return balance, 9999
    today = datetime.now().date().isoformat()
    if last_reset != today:
        cursor.execute("UPDATE users SET daily_requests_used = 0, daily_reset = ? WHERE user_id = ?", (today, user_id))
        used = 0
    return max(0, 10 - used), 10


@db_operation
def spend_text_token(conn, cursor, user_id):
    today = datetime.now().date().isoformat()
    cursor.execute("UPDATE users SET daily_requests_used = daily_requests_used + 1, daily_reset = ? WHERE user_id = ?", (today, user_id))


@db_operation
def get_week_images_used(conn, cursor, user_id):
    cursor.execute("SELECT plan, week_images_used, week_start, tokens FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        return 0, 2
    plan = row[0] or "basic"
    used = row[1] or 0
    week_start = row[2]
    balance = row[3] or 0
    if balance > 0:
        return used, 9999
    now = datetime.now()
    monday = (now - timedelta(days=now.weekday())).date().isoformat()
    if week_start != monday:
        cursor.execute("UPDATE users SET week_images_used = 0, week_start = ? WHERE user_id = ?", (monday, user_id))
        used = 0
    return used, 2


@db_operation
def use_week_image(conn, cursor, user_id):
    now = datetime.now()
    monday = (now - timedelta(days=now.weekday())).date().isoformat()
    cursor.execute("UPDATE users SET week_images_used = week_images_used + 1, week_start = ? WHERE user_id = ?", (monday, user_id))


# ===== ТРИАЛ =====
@db_operation
def has_trial(conn, cursor, user_id):
    cursor.execute("SELECT trial_start, trial_active FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        return False
    trial_start = row[0]
    trial_active = row[1] or 0
    if not trial_start or not trial_active:
        return False
    start_date = datetime.fromisoformat(trial_start)
    return (datetime.now() - start_date).days < 30


@db_operation
def activate_trial(conn, cursor, user_id):
    cursor.execute("UPDATE users SET trial_start = ?, trial_active = 1, tokens = tokens + 30 WHERE user_id = ?",
                   (datetime.now().isoformat(), user_id))


# ===== КАРТИНКИ =====
@db_operation
def save_image_to_history(conn, cursor, user_id, prompt, enhanced_prompt, model, image_data):
    session_id = secrets.token_hex(8)
    cursor.execute("""
        INSERT INTO images_history (user_id, prompt, enhanced_prompt, model, image_data, session_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, prompt, enhanced_prompt, model, image_data, session_id, datetime.now().isoformat()))
    return cursor.lastrowid, session_id


@db_operation
def get_last_image(conn, cursor, user_id):
    cursor.execute("SELECT * FROM images_history WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


# ===== РЕФЕРАЛЫ =====
@db_operation
def add_referral(conn, cursor, referrer_id, referred_id):
    if referrer_id == referred_id:
        return False, "Нельзя пригласить себя!"
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (referred_id,))
    if not cursor.fetchone():
        return False, "Пользователь не найден!"
    cursor.execute("SELECT referrer_id FROM referrals WHERE referred_id = ?", (referred_id,))
    if cursor.fetchone():
        return False, "Уже приглашён!"
    cursor.execute("INSERT INTO referrals (referrer_id, referred_id, joined) VALUES (?, ?, ?)",
                   (referrer_id, referred_id, datetime.now().isoformat()))
    cursor.execute("UPDATE users SET tokens = tokens + 20 WHERE user_id = ?", (referrer_id,))
    _schedule_db_backup()

    try:
        from utils.user_storage import save_user_referrals, save_user_tokens
        cursor.execute("SELECT referred_id, joined FROM referrals WHERE referrer_id = ?", (referrer_id,))
        rows = cursor.fetchall()
        referrals = [{"referred_id": r[0], "joined": r[1]} for r in rows]
        save_user_referrals(referrer_id, referrals)

        cursor.execute("SELECT tokens, plan, premium_until FROM users WHERE user_id = ?", (referrer_id,))
        u = cursor.fetchone()
        if u:
            save_user_tokens(referrer_id, u[0], u[1], u[2])
    except Exception as e:
        print(f"⚠️ save_user_referrals: {e}")

    return True, "✅ +20 токенов!"


@db_operation
def get_referral_count(conn, cursor, user_id):
    cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
    return cursor.fetchone()[0] or 0


# ===== ПРОМОКОДЫ =====
@db_operation
def use_promocode(conn, cursor, code, user_id):
    code = code.strip().upper()
    cursor.execute("SELECT id, bonus_tokens, max_uses, used FROM promocodes WHERE code = ? AND expires_at > datetime('now')", (code,))
    promo = cursor.fetchone()
    if not promo:
        return False, "❌ Промокод не найден"
    if promo['used'] >= promo['max_uses']:
        return False, "❌ Промокод использован"
    cursor.execute("SELECT id FROM promocode_uses WHERE promocode_id = ? AND user_id = ?", (promo['id'], user_id))
    if cursor.fetchone():
        return False, "❌ Вы уже использовали"
    cursor.execute("INSERT INTO promocode_uses (promocode_id, user_id, used_at) VALUES (?, ?, ?)",
                   (promo['id'], user_id, datetime.now().isoformat()))
    cursor.execute("UPDATE promocodes SET used = used + 1 WHERE id = ?", (promo['id'],))
    if promo['bonus_tokens'] > 0:
        cursor.execute("UPDATE users SET tokens = tokens + ? WHERE user_id = ?", (promo['bonus_tokens'], user_id))
        _schedule_db_backup()
        try:
            from utils.user_storage import save_user_tokens
            cursor.execute("SELECT tokens, plan, premium_until FROM users WHERE user_id = ?", (user_id,))
            u = cursor.fetchone()
            if u:
                save_user_tokens(user_id, u[0], u[1], u[2])
        except Exception as e:
            print(f"⚠️ save_user_tokens: {e}")
    return True, f"✅ +{promo['bonus_tokens']} токенов!"


# ===== ПЛАТЕЖИ =====
@db_operation
def create_payment(conn, cursor, user_id, stars, payload, plan):
    cursor.execute("INSERT INTO payments (user_id, stars_amount, telegram_payload, status, timestamp, plan) VALUES (?, ?, ?, ?, ?, ?)",
                   (user_id, stars, payload, "pending", datetime.now().isoformat(), plan))
    try:
        from utils.user_storage import save_user_payments
        cursor.execute("SELECT stars_amount, plan, status, timestamp FROM payments WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall()
        payments = [{"stars": r[0], "plan": r[1], "status": r[2], "timestamp": r[3]} for r in rows]
        save_user_payments(user_id, payments)
    except Exception as e:
        print(f"⚠️ save_user_payments: {e}")


@db_operation
def complete_payment(conn, cursor, payload):
    cursor.execute("UPDATE payments SET status = 'completed' WHERE telegram_payload = ?", (payload,))
    cursor.execute("SELECT user_id, stars_amount, plan FROM payments WHERE telegram_payload = ?", (payload,))
    row = cursor.fetchone()

    if row:
        try:
            from utils.user_storage import save_user_payments
            user_id = row[0]
            cursor.execute("SELECT stars_amount, plan, status, timestamp FROM payments WHERE user_id = ?", (user_id,))
            rows = cursor.fetchall()
            payments = [{"stars": r[0], "plan": r[1], "status": r[2], "timestamp": r[3]} for r in rows]
            save_user_payments(user_id, payments)
        except Exception as e:
            print(f"⚠️ save_user_payments: {e}")

    return row


@db_operation
def is_admin(conn, cursor, user_id):
    cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    return cursor.fetchone() is not None


@db_operation
def add_admin(conn, cursor, user_id):
    cursor.execute("INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)",
                   (user_id, datetime.now().isoformat()))


@db_operation
def add_premium(conn, cursor, user_id, days, plan, paid=False):
    new_date = (datetime.now() + timedelta(days=days)).isoformat()
    cursor.execute("UPDATE users SET premium_until = ?, plan = ? WHERE user_id = ?", (new_date, plan, user_id))
    if paid:
        cursor.execute("UPDATE users SET paid_premium = 1 WHERE user_id = ?", (user_id,))
    _schedule_db_backup()
    try:
        from utils.user_storage import save_user_tokens
        cursor.execute("SELECT tokens FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            save_user_tokens(user_id, row[0], plan, new_date)
    except Exception as e:
        print(f"⚠️ save_user_tokens: {e}")


@db_operation
def block_user(conn, cursor, user_id):
    cursor.execute("UPDATE users SET is_blocked = 1 WHERE user_id = ?", (user_id,))


@db_operation
def unblock_user(conn, cursor, user_id):
    cursor.execute("UPDATE users SET is_blocked = 0 WHERE user_id = ?", (user_id,))


@db_operation
def get_stats(conn, cursor):
    cursor.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(tokens) FROM users")
    total_tokens = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM users WHERE plan IN ('premium', 'premium_plus')")
    premium_users = cursor.fetchone()[0] or 0
    return total, total_tokens, premium_users


# ===== ПОДПИСКИ =====
@db_operation
def get_expiring_subscriptions(conn, cursor):
    now = datetime.now()
    in_4_days = (now + timedelta(days=4)).isoformat()
    cursor.execute("""
        SELECT user_id, plan, premium_until FROM users
        WHERE plan IN ('premium', 'premium_plus')
        AND premium_until > ? AND premium_until <= ?
    """, (now.isoformat(), in_4_days))
    return cursor.fetchall()


@db_operation
def mark_subscription_notified(conn, cursor, user_id):
    today = datetime.now().date().isoformat()
    cursor.execute("INSERT OR REPLACE INTO subscription_notifications (user_id, last_notified) VALUES (?, ?)",
                   (user_id, today))


@db_operation
def was_subscription_notified_today(conn, cursor, user_id):
    today = datetime.now().date().isoformat()
    cursor.execute("SELECT last_notified FROM subscription_notifications WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        return False
    return row[0] == today


# ===== НАПОМИНАНИЯ =====
@db_operation
def add_reminder(conn, cursor, user_id, text, time_str):
    try:
        dt_local = datetime.fromisoformat(time_str)
        dt_utc = dt_local - timedelta(hours=TIMEZONE_OFFSET)
        time_str = dt_utc.isoformat()
    except Exception as e:
        print(f"⚠️ Сдвиг времени: {e}")
    cursor.execute("INSERT INTO reminders (user_id, text, time, created_at) VALUES (?, ?, ?, ?)",
                   (user_id, text, time_str, datetime.now().isoformat()))
    reminder_id = cursor.lastrowid

    try:
        from utils.user_storage import save_user_reminders
        cursor.execute("SELECT id, text, time FROM reminders WHERE user_id = ? AND sent = 0", (user_id,))
        rows = cursor.fetchall()
        reminders = [{"id": r[0], "text": r[1], "time": r[2]} for r in rows]
        save_user_reminders(user_id, reminders)
    except Exception as e:
        print(f"⚠️ save_user_reminders: {e}")

    return reminder_id


@db_operation
def get_user_reminders(conn, cursor, user_id):
    cursor.execute("SELECT * FROM reminders WHERE user_id = ? AND sent = 0 ORDER BY time ASC", (user_id,))
    rows = cursor.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            dt_utc = datetime.fromisoformat(d['time'])
            dt_local = dt_utc + timedelta(hours=TIMEZONE_OFFSET)
            d['time_local'] = dt_local.isoformat()
        except Exception:
            d['time_local'] = d['time']
        result.append(d)
    return result


@db_operation
def delete_reminder(conn, cursor, reminder_id):
    cursor.execute("SELECT user_id FROM reminders WHERE id = ?", (reminder_id,))
    row = cursor.fetchone()
    user_id = row[0] if row else None

    cursor.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))

    if user_id:
        try:
            from utils.user_storage import save_user_reminders
            cursor.execute("SELECT id, text, time FROM reminders WHERE user_id = ? AND sent = 0", (user_id,))
            rows = cursor.fetchall()
            reminders = [{"id": r[0], "text": r[1], "time": r[2]} for r in rows]
            save_user_reminders(user_id, reminders)
        except Exception as e:
            print(f"⚠️ save_user_reminders: {e}")


@db_operation
def delete_reminder_by_text(conn, cursor, user_id, text):
    cursor.execute("DELETE FROM reminders WHERE user_id = ? AND text LIKE ?", (user_id, f"%{text}%"))
    try:
        from utils.user_storage import save_user_reminders
        cursor.execute("SELECT id, text, time FROM reminders WHERE user_id = ? AND sent = 0", (user_id,))
        rows = cursor.fetchall()
        reminders = [{"id": r[0], "text": r[1], "time": r[2]} for r in rows]
        save_user_reminders(user_id, reminders)
    except Exception as e:
        print(f"⚠️ save_user_reminders: {e}")


@db_operation
def delete_all_reminders(conn, cursor, user_id):
    cursor.execute("DELETE FROM reminders WHERE user_id = ?", (user_id,))
    try:
        from utils.user_storage import save_user_reminders
        save_user_reminders(user_id, [])
    except Exception as e:
        print(f"⚠️ save_user_reminders: {e}")


# ===== НАСТРОЙКИ =====
@db_operation
def get_setting(conn, cursor, key):
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    return row[0] if row else None


@db_operation
def set_setting(conn, cursor, key, value):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))


# ===== МОДЕЛИ =====
@db_operation
def get_model_setting(conn, cursor, task):
    cursor.execute("SELECT model FROM model_settings WHERE task = ?", (task,))
    row = cursor.fetchone()
    return row[0] if row else None


@db_operation
def set_model_setting(conn, cursor, task, model):
    cursor.execute("INSERT OR REPLACE INTO model_settings (task, model, updated_at) VALUES (?, ?, ?)",
                   (task, model, datetime.now().isoformat()))


@db_operation
def get_all_model_settings(conn, cursor):
    cursor.execute("SELECT task, model FROM model_settings")
    return {row[0]: row[1] for row in cursor.fetchall()}


# ===== ТАРИФЫ =====
@db_operation
def get_tariffs(conn, cursor, kind=None):
    if kind:
        cursor.execute("SELECT * FROM tariffs WHERE active = 1 AND kind = ? ORDER BY sort_order", (kind,))
    else:
        cursor.execute("SELECT * FROM tariffs WHERE active = 1 ORDER BY kind, sort_order")
    return [dict(r) for r in cursor.fetchall()]


@db_operation
def add_tariff(conn, cursor, kind, name, price_rub, stars, tokens, days=0):
    cursor.execute("INSERT INTO tariffs (kind, name, price_rub, stars, tokens, days, sort_order) VALUES (?, ?, ?, ?, ?, ?, 99)",
                   (kind, name, price_rub, stars, tokens, days))


@db_operation
def update_tariff(conn, cursor, tariff_id, **fields):
    if not fields:
        return
    set_parts = []
    values = []
    for k, v in fields.items():
        set_parts.append(f"{k} = ?")
        values.append(v)
    values.append(tariff_id)
    cursor.execute(f"UPDATE tariffs SET {', '.join(set_parts)} WHERE id = ?", values)


@db_operation
def delete_tariff(conn, cursor, tariff_id):
    cursor.execute("DELETE FROM tariffs WHERE id = ?", (tariff_id,))


@db_operation
def get_tariff(conn, cursor, tariff_id):
    cursor.execute("SELECT * FROM tariffs WHERE id = ?", (tariff_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


# ===== СЛУЖЕБНОЕ =====
def do_backup():
    try:
        from backup import GitHubBackup
        GitHubBackup().backup_all(reason='после изменения')
    except Exception:
        pass


def get_queue_info():
    size = _db_queue.qsize()
    status = "✅ Работает" if _db_thread and _db_thread.is_alive() else "❌ Остановлен"
    return f"📊 Очередь БД: {size} задач, поток: {status}"
