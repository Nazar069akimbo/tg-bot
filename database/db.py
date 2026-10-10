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

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            status TEXT DEFAULT 'open',
            created_at TEXT,
            updated_at TEXT
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS support_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER,
            sender TEXT,
            text TEXT,
            created_at TEXT
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT,
            user_id INTEGER,
            sent INTEGER DEFAULT 0,
            created_at TEXT
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


def restore_from_user_folders():
    """Восстанавливает токены/план из папок.
    Если у пользователя несколько папок — берёт МАКСИМУМ токенов."""
    base = 'data/users'
    if not os.path.exists(base):
        return 0

    collected = {}

    for folder in os.listdir(base):
        folder_path = os.path.join(base, folder)
        if not os.path.isdir(folder_path):
            continue

        id_file = os.path.join(folder_path, "_id.txt")
        tokens_file = os.path.join(folder_path, "tokens.json")
        profile_file = os.path.join(folder_path, "profile.json")

        if not os.path.exists(id_file):
            continue

        try:
            with open(id_file, "r", encoding="utf-8") as f:
                user_id = int(f.read().strip())
        except Exception:
            continue

        tokens = 0
        plan = "basic"
        premium_until = None

        if os.path.exists(tokens_file):
            try:
                with open(tokens_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    tokens = data.get("tokens", 0) or 0
                    plan = data.get("plan", "basic")
                    premium_until = data.get("premium_until")
            except Exception:
                pass

        name = None
        if os.path.exists(profile_file):
            try:
                with open(profile_file, "r", encoding="utf-8") as f:
                    name = json.load(f).get("name")
            except Exception:
                pass

        if user_id in collected:
            if tokens > collected[user_id]["tokens"]:
                collected[user_id] = {
                    "tokens": tokens,
                    "plan": plan,
                    "premium_until": premium_until,
                    "name": name,
                }
        else:
            collected[user_id] = {
                "tokens": tokens,
                "plan": plan,
                "premium_until": premium_until,
                "name": name,
            }

    restored = 0
    with db_connection() as conn:
        cursor = conn.cursor()

        for user_id, info in collected.items():
            tokens = info["tokens"]
            plan = info["plan"]
            premium_until = info["premium_until"]
            name = info["name"]

            cursor.execute("SELECT user_id, tokens FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()

            # Папка — источник правды: перезаписываем БД, если в папке есть токены
            if not tokens and row and row[1] and row[1] > 0:
                print(f"⏭ {name or user_id}: папка пустая, в БД {row[1]}, пропуск")
                continue

            if row:
                cursor.execute("""
                    UPDATE users SET tokens = ?, plan = ?, premium_until = ?, trial_active = 1
                    WHERE user_id = ?
                """, (tokens, plan, premium_until, user_id))
            else:
                cursor.execute("""
                    INSERT INTO users (user_id, username, joined, trial_start, trial_active,
                                       tokens, plan, premium_until, daily_reset)
                    VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
                """, (user_id, name or str(user_id),
                      datetime.now().isoformat(), datetime.now().isoformat(),
                      tokens, plan, premium_until,
                      datetime.now().date().isoformat()))

            restored += 1
            print(f"✅ Восстановлен {name or user_id}: {tokens} токенов")

    return restored


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
    return True, "✅ +20 токенов!"


@db_operation
def get_referral_count(conn, cursor, user_id):
    cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
    return cursor.fetchone()[0] or 0


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
    return True, f"✅ +{promo['bonus_tokens']} токенов!"


@db_operation
def create_payment(conn, cursor, user_id, stars, payload, plan):
    cursor.execute("INSERT INTO payments (user_id, stars_amount, telegram_payload, status, timestamp, plan) VALUES (?, ?, ?, ?, ?, ?)",
                   (user_id, stars, payload, "pending", datetime.now().isoformat(), plan))


@db_operation
def complete_payment(conn, cursor, payload):
    cursor.execute("UPDATE payments SET status = 'completed' WHERE telegram_payload = ?", (payload,))
    cursor.execute("SELECT user_id, stars_amount, plan FROM payments WHERE telegram_payload = ?", (payload,))
    return cursor.fetchone()


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
    return cursor.lastrowid


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
    cursor.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))


@db_operation
def delete_reminder_by_text(conn, cursor, user_id, text):
    cursor.execute("DELETE FROM reminders WHERE user_id = ? AND text LIKE ?", (user_id, f"%{text}%"))


@db_operation
def delete_all_reminders(conn, cursor, user_id):
    cursor.execute("DELETE FROM reminders WHERE user_id = ?", (user_id,))


@db_operation
def get_setting(conn, cursor, key):
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    return row[0] if row else None


@db_operation
def set_setting(conn, cursor, key, value):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))


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


@db_operation
def search_users(conn, cursor, query=None, filter_type=None, limit=50):
    sql = "SELECT user_id, username, tokens, plan, joined, is_blocked FROM users WHERE 1=1"
    params = []

    if query:
        sql += """ AND (
            username LIKE ?
            OR CAST(user_id AS TEXT) LIKE ?
            OR user_id IN (SELECT user_id FROM user_memory WHERE name LIKE ?)
        )"""
        params.append(f"%{query}%")
        params.append(f"%{query}%")
        params.append(f"%{query}%")

    if filter_type == "premium":
        sql += " AND plan IN ('premium', 'premium_plus')"
    elif filter_type == "basic":
        sql += " AND plan = 'basic'"
    elif filter_type == "recent":
        sql += " AND joined > datetime('now', '-7 days')"
    elif filter_type == "rich":
        sql += " AND tokens > 1000"
    elif filter_type == "poor":
        sql += " AND tokens < 100"

    sql += " ORDER BY tokens DESC LIMIT ?"
    params.append(limit)

    cursor.execute(sql, params)
    return [dict(r) for r in cursor.fetchall()]


@db_operation
def get_users_count(conn, cursor):
    cursor.execute("SELECT COUNT(*) FROM users")
    return cursor.fetchone()[0] or 0


@db_operation
def get_users_count_today(conn, cursor):
    cursor.execute("SELECT COUNT(*) FROM users WHERE joined > datetime('now', '-1 day')")
    return cursor.fetchone()[0] or 0


@db_operation
def get_users_count_week(conn, cursor):
    cursor.execute("SELECT COUNT(*) FROM users WHERE joined > datetime('now', '-7 days')")
    return cursor.fetchone()[0] or 0


@db_operation
def get_premium_count(conn, cursor):
    cursor.execute("SELECT COUNT(*) FROM users WHERE plan IN ('premium', 'premium_plus')")
    return cursor.fetchone()[0] or 0


@db_operation
def create_support_ticket(conn, cursor, user_id, username, first_message):
    cursor.execute("""
        INSERT INTO support_tickets (user_id, username, status, created_at, updated_at)
        VALUES (?, ?, 'open', ?, ?)
    """, (user_id, username, datetime.now().isoformat(), datetime.now().isoformat()))
    ticket_id = cursor.lastrowid

    cursor.execute("""
        INSERT INTO support_messages (ticket_id, sender, text, created_at)
        VALUES (?, 'user', ?, ?)
    """, (ticket_id, first_message, datetime.now().isoformat()))

    return ticket_id


@db_operation
def add_support_message(conn, cursor, ticket_id, sender, text):
    cursor.execute("""
        INSERT INTO support_messages (ticket_id, sender, text, created_at)
        VALUES (?, ?, ?, ?)
    """, (ticket_id, sender, text, datetime.now().isoformat()))

    cursor.execute("UPDATE support_tickets SET updated_at = ? WHERE id = ?",
                   (datetime.now().isoformat(), ticket_id))
    return cursor.lastrowid


@db_operation
def get_support_tickets(conn, cursor, status=None, limit=30):
    if status:
        cursor.execute("""
            SELECT * FROM support_tickets WHERE status = ?
            ORDER BY updated_at DESC LIMIT ?
        """, (status, limit))
    else:
        cursor.execute("""
            SELECT * FROM support_tickets
            ORDER BY updated_at DESC LIMIT ?
        """, (limit,))
    return [dict(r) for r in cursor.fetchall()]


@db_operation
def get_ticket_messages(conn, cursor, ticket_id, limit=100):
    cursor.execute("""
        SELECT * FROM support_messages WHERE ticket_id = ?
        ORDER BY id ASC LIMIT ?
    """, (ticket_id, limit))
    return [dict(r) for r in cursor.fetchall()]


@db_operation
def close_ticket(conn, cursor, ticket_id):
    cursor.execute("UPDATE support_tickets SET status = 'closed', updated_at = ? WHERE id = ?",
                   (datetime.now().isoformat(), ticket_id))


@db_operation
def get_user_ticket(conn, cursor, user_id):
    cursor.execute("""
        SELECT * FROM support_tickets WHERE user_id = ? AND status = 'open'
        ORDER BY id DESC LIMIT 1
    """, (user_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


@db_operation
def add_admin_notification(conn, cursor, text, user_id=None):
    cursor.execute("""
        INSERT INTO admin_notifications (text, user_id, created_at)
        VALUES (?, ?, ?)
    """, (text, user_id, datetime.now().isoformat()))
    return cursor.lastrowid


@db_operation
def get_pending_notifications(conn, cursor, limit=20):
    cursor.execute("""
        SELECT * FROM admin_notifications WHERE sent = 0
        ORDER BY id ASC LIMIT ?
    """, (limit,))
    return [dict(r) for r in cursor.fetchall()]


@db_operation
def mark_notification_sent(conn, cursor, notif_id):
    cursor.execute("UPDATE admin_notifications SET sent = 1 WHERE id = ?", (notif_id,))


@db_operation
def create_test_users(conn, cursor, count=10):
    names = ["Тест1", "Тест2", "Тест3", "Тест4", "Тест5",
             "Тест6", "Тест7", "Тест8", "Тест9", "Тест10"]
    plans = ["basic", "basic", "premium", "basic", "premium_plus",
             "basic", "premium", "basic", "premium_plus", "basic"]
    tokens_list = [0, 50, 100, 500, 1000, 3000, 200, 0, 800, 150]

    for i in range(count):
        uid = 900000000 + i
        name = names[i % len(names)]
        plan = plans[i % len(plans)]
        tokens = tokens_list[i % len(tokens_list)]
        premium_until = (datetime.now() + timedelta(days=30)).isoformat() if plan != "basic" else None
        joined = (datetime.now() - timedelta(days=i)).isoformat()

        cursor.execute("""
            INSERT OR REPLACE INTO users
            (user_id, username, joined, tokens, plan, premium_until, trial_start, trial_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """, (uid, name, joined, tokens, plan, premium_until, joined))

    return count


@db_operation
def delete_test_users(conn, cursor):
    cursor.execute("DELETE FROM users WHERE user_id >= 900000000")
    return cursor.rowcount


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
