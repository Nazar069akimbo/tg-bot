import sqlite3
import os
import json
import secrets
import time
import threading
import queue
from datetime import datetime, timedelta
from contextlib import contextmanager

DB_PATH = 'data/repsolver.db'
os.makedirs('data', exist_ok=True)

# ===== ОЧЕРЕДЬ ЗАПРОСОВ =====
_db_queue = queue.Queue()
_db_thread = None
_db_running = True

def _db_worker():
    """Фоновый поток, обрабатывающий запросы к БД"""
    conn = None
    while _db_running:
        try:
            task = _db_queue.get(timeout=5)
            if task is None:
                continue
            
            func, args, kwargs, result_queue, error_queue = task
            
            try:
                if conn is None:
                    conn = sqlite3.connect(DB_PATH, timeout=60)
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
    """Отправляет запрос в очередь и ждёт результат (ЭКСПОРТИРУЕТСЯ)"""
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

# ===== ИНИЦИАЛИЗАЦИЯ =====
def init_db():
    def _init(conn, cursor):
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            joined TEXT,
            tokens INTEGER DEFAULT 0,
            trial_start TEXT,
            trial_active INTEGER DEFAULT 0,
            text_requests INTEGER DEFAULT 0,
            max_text_requests INTEGER DEFAULT 10,
            text_requests_reset TEXT,
            is_blocked INTEGER DEFAULT 0,
            plan TEXT DEFAULT "basic",
            premium_until TEXT,
            total_requests INTEGER DEFAULT 0,
            image_requests INTEGER DEFAULT 0,
            last_image_reset TEXT,
            referral_bonus_images INTEGER DEFAULT 0,
            referral_bonus_requests INTEGER DEFAULT 0,
            paid_premium INTEGER DEFAULT 0,
            bonus_images INTEGER DEFAULT 0,
            bonus_requests INTEGER DEFAULT 0,
            last_checkin TEXT,
            checkin_streak INTEGER DEFAULT 0,
            total_spent INTEGER DEFAULT 0
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_memory (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            favorite_style TEXT,
            favorite_colors TEXT,
            preferred_model TEXT,
            last_prompt TEXT,
            context_history TEXT,
            preferences TEXT,
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
            previous_id INTEGER,
            session_id TEXT,
            edit_type TEXT,
            edit_text TEXT,
            version INTEGER DEFAULT 1,
            created_at TEXT
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS edit_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            session_id TEXT UNIQUE,
            original_image_id INTEGER,
            current_image_id INTEGER,
            is_active INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER,
            joined TEXT,
            bonus_given INTEGER DEFAULT 0,
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
            bonus_images INTEGER DEFAULT 0,
            bonus_requests INTEGER DEFAULT 0,
            max_uses INTEGER DEFAULT 1,
            used INTEGER DEFAULT 0,
            created_by INTEGER,
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
            repeat TEXT,
            created_at TEXT
        )
        ''')
        
        default_settings = [
            ('free_input_chars', '500'),
            ('free_output_words', '50'),
            ('premium_input_chars', '3000'),
            ('premium_output_words', '300'),
            ('premium_deluxe_input_chars', '5000'),
            ('premium_deluxe_output_words', '500'),
            ('image_limit_free', '3'),
            ('image_limit_premium', '20'),
            ('image_limit_premium_deluxe', '50')
        ]
        for key, value in default_settings:
            cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
        
        ADMIN_ID = int(os.getenv('ADMIN_ID', 6957852385))
        cursor.execute("INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)", 
                       (ADMIN_ID, datetime.now().isoformat()))
        
        print("✅ База данных инициализирована")
    
    _execute_db(_init)

def migrate_db():
    def _migrate(conn, cursor):
        cursor.execute("PRAGMA table_info(promocodes)")
        cols = [row[1] for row in cursor.fetchall()]
        
        for col in ['bonus_tokens', 'bonus_images', 'bonus_requests', 'max_uses', 'used']:
            if col not in cols:
                cursor.execute(f"ALTER TABLE promocodes ADD COLUMN {col} INTEGER DEFAULT 0")
                print(f"✅ Добавлена {col}")
        
        print("✅ Миграция выполнена")
    
    try:
        _execute_db(_migrate)
    except Exception as e:
        print(f"⚠️ Ошибка миграции: {e}")

# ===== ФУНКЦИИ БЕЗ ДЕКОРАТОРА (СИНХРОННЫЕ) =====
def get_user_sync(user_id):
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def set_user_name_sync(user_id, name):
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM user_memory WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO user_memory (user_id, created_at, updated_at, context_history)
            VALUES (?, ?, ?, ?)
        """, (user_id, datetime.now().isoformat(), datetime.now().isoformat(), json.dumps([])))
    cursor.execute("UPDATE user_memory SET name = ?, updated_at = ? WHERE user_id = ?", 
                   (name, datetime.now().isoformat(), user_id))
    conn.commit()
    conn.close()

# ===== ОСНОВНЫЕ ФУНКЦИИ (С ДЕКОРАТОРОМ) =====

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
        INSERT INTO users (user_id, username, joined, trial_start, trial_active, last_image_reset)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, username, now, now, 1, now))
    return True

def force_create_user(user_id, username=None):
    try:
        user = get_user_sync(user_id)
        if user:
            return user
        create_user(user_id, username or str(user_id))
        set_user_name_sync(user_id, username or str(user_id))
        return get_user_sync(user_id)
    except Exception as e:
        print(f"❌ Ошибка force_create_user: {e}")
        return None

@db_operation
def get_tokens(conn, cursor, user_id):
    cursor.execute("SELECT tokens FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else 0

@db_operation
def add_tokens(conn, cursor, user_id, amount):
    cursor.execute("UPDATE users SET tokens = tokens + ? WHERE user_id = ?", (amount, user_id))

@db_operation
def spend_tokens(conn, cursor, user_id, amount):
    cursor.execute("SELECT tokens FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row and row[0] >= amount:
        cursor.execute("UPDATE users SET tokens = tokens - ? WHERE user_id = ?", (amount, user_id))
        return True
    return False

@db_operation
def get_user_memory(conn, cursor, user_id):
    cursor.execute("SELECT * FROM user_memory WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return dict(row) if row else None

@db_operation
def init_user_memory(conn, cursor, user_id):
    cursor.execute("""
        INSERT OR IGNORE INTO user_memory (user_id, created_at, updated_at, context_history)
        VALUES (?, ?, ?, ?)
    """, (user_id, datetime.now().isoformat(), datetime.now().isoformat(), json.dumps([])))

@db_operation
def update_user_memory(conn, cursor, user_id, data):
    cursor.execute("SELECT user_id FROM user_memory WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        init_user_memory(user_id)
    
    set_parts = []
    values = []
    for key, value in data.items():
        set_parts.append(f"{key} = ?")
        if isinstance(value, (dict, list)):
            values.append(json.dumps(value))
        else:
            values.append(value)
    
    if not set_parts:
        return
    set_parts.append("updated_at = ?")
    values.append(datetime.now().isoformat())
    values.append(user_id)
    query = f"UPDATE user_memory SET {', '.join(set_parts)} WHERE user_id = ?"
    cursor.execute(query, values)

def set_user_name(user_id, name):
    set_user_name_sync(user_id, name)

def add_to_context(user_id, prompt, image_id=None, edit_type=None):
    memory = get_user_memory(user_id)
    if not memory:
        init_user_memory(user_id)
        memory = get_user_memory(user_id)
    history = json.loads(memory.get('context_history', '[]')) if memory else []
    history.append({'prompt': prompt, 'image_id': image_id, 'edit_type': edit_type, 'timestamp': datetime.now().isoformat()})
    if len(history) > 20:
        history = history[-20:]
    update_user_memory(user_id, {'context_history': json.dumps(history)})

@db_operation
def save_image_to_history(conn, cursor, user_id, prompt, enhanced_prompt, model, image_data, previous_id=None, session_id=None, edit_type=None, edit_text=None):
    if not session_id:
        session_id = secrets.token_hex(8)
    cursor.execute("SELECT COUNT(*) + 1 FROM images_history WHERE user_id = ? AND session_id = ?", (user_id, session_id))
    version = cursor.fetchone()[0] or 1
    cursor.execute("""
        INSERT INTO images_history (user_id, prompt, enhanced_prompt, model, image_data, previous_id, session_id, edit_type, edit_text, version, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, prompt, enhanced_prompt, model, image_data, previous_id, session_id, edit_type, edit_text, version, datetime.now().isoformat()))
    image_id = cursor.lastrowid
    add_to_context(user_id, prompt, image_id, edit_type)
    return image_id, session_id

@db_operation
def get_last_image(conn, cursor, user_id):
    cursor.execute("SELECT * FROM images_history WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
    row = cursor.fetchone()
    return dict(row) if row else None

@db_operation
def get_image_by_id(conn, cursor, image_id):
    cursor.execute("SELECT * FROM images_history WHERE id = ?", (image_id,))
    row = cursor.fetchone()
    return dict(row) if row else None

@db_operation
def get_image_chain_by_session(conn, cursor, user_id, session_id):
    cursor.execute("SELECT * FROM images_history WHERE user_id = ? AND session_id = ? ORDER BY id ASC", (user_id, session_id))
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

@db_operation
def get_edit_version(conn, cursor, user_id, session_id):
    cursor.execute("SELECT COUNT(*) FROM images_history WHERE user_id = ? AND session_id = ?", (user_id, session_id))
    return cursor.fetchone()[0] or 0

@db_operation
def get_text_requests(conn, cursor, user_id):
    cursor.execute("SELECT text_requests, max_text_requests FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        return 0, 10
    return row[0] if row[0] else 0, row[1] if row[1] else 10

@db_operation
def reset_text_requests_if_needed(conn, cursor, user_id):
    cursor.execute("SELECT text_requests_reset FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("UPDATE users SET text_requests = 0, text_requests_reset = ? WHERE user_id = ?", 
                      (datetime.now().isoformat(), user_id))
        return
    last_reset = row[0]
    if not last_reset:
        cursor.execute("UPDATE users SET text_requests = 0, text_requests_reset = ? WHERE user_id = ?", 
                      (datetime.now().isoformat(), user_id))
        return
    last_date = datetime.fromisoformat(last_reset)
    if last_date.date() < datetime.now().date():
        cursor.execute("UPDATE users SET text_requests = 0, text_requests_reset = ? WHERE user_id = ?", 
                      (datetime.now().isoformat(), user_id))

@db_operation
def add_text_request(conn, cursor, user_id):
    cursor.execute("UPDATE users SET text_requests = text_requests + 1 WHERE user_id = ?", (user_id,))

def can_request_text(user_id):
    reset_text_requests_if_needed(user_id)
    used, max_req = get_text_requests(user_id)
    return used < max_req, max_req - used

@db_operation
def has_trial(conn, cursor, user_id):
    cursor.execute("SELECT trial_start FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        return False
    trial_start = row[0]
    if not trial_start:
        return False
    start_date = datetime.fromisoformat(trial_start)
    return (datetime.now() - start_date).days < 3

@db_operation
def activate_trial(conn, cursor, user_id):
    cursor.execute("UPDATE users SET trial_start = ?, tokens = tokens + 20 WHERE user_id = ?", 
                  (datetime.now().isoformat(), user_id))

@db_operation
def get_trial_remaining(conn, cursor, user_id):
    cursor.execute("SELECT trial_start FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        return 0
    trial_start = row[0]
    if not trial_start:
        return 0
    start_date = datetime.fromisoformat(trial_start)
    days_passed = (datetime.now() - start_date).days
    return max(0, 3 - days_passed)

@db_operation
def add_referral(conn, cursor, referrer_id, referred_id):
    if referrer_id == referred_id:
        return False, "Нельзя пригласить себя!"
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (referrer_id,))
    if not cursor.fetchone():
        return False, "Реферер не найден!"
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (referred_id,))
    if not cursor.fetchone():
        return False, "Пользователь не найден!"
    cursor.execute("SELECT referrer_id FROM referrals WHERE referred_id = ?", (referred_id,))
    if cursor.fetchone():
        return False, "Уже приглашён!"
    cursor.execute("INSERT INTO referrals (referrer_id, referred_id, joined) VALUES (?, ?, ?)",
                  (referrer_id, referred_id, datetime.now().isoformat()))
    add_tokens(referrer_id, 20)
    return True, "✅ +20 токенов!"

@db_operation
def get_referral_count(conn, cursor, user_id):
    cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
    return cursor.fetchone()[0] or 0

@db_operation
def use_promocode(conn, cursor, code, user_id):
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
    cursor.execute("SELECT SUM(total_requests) FROM users")
    total_requests = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(image_requests) FROM users")
    total_images = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM users WHERE plan IN ('premium', 'premium_deluxe')")
    premium_users = cursor.fetchone()[0] or 0
    return total, total_tokens, total_requests, total_images, premium_users

@db_operation
def add_reminder(conn, cursor, user_id, text, time_str, repeat=None):
    cursor.execute("""
        INSERT INTO reminders (user_id, text, time, repeat, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, text, time_str, repeat, datetime.now().isoformat()))
    return cursor.lastrowid

@db_operation
def get_due_reminders(conn, cursor):
    now = datetime.now().isoformat()
    cursor.execute("SELECT * FROM reminders WHERE sent = 0 AND time <= ? ORDER BY time ASC", (now,))
    return cursor.fetchall()

@db_operation
def mark_reminder_sent(conn, cursor, reminder_id):
    cursor.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (reminder_id,))

@db_operation
def get_user_reminders(conn, cursor, user_id):
    cursor.execute("SELECT * FROM reminders WHERE user_id = ? AND sent = 0 ORDER BY time ASC", (user_id,))
    return cursor.fetchall()

@db_operation
def delete_reminder(conn, cursor, reminder_id, user_id):
    cursor.execute("DELETE FROM reminders WHERE id = ? AND user_id = ?", (reminder_id, user_id))

@db_operation
def get_setting(conn, cursor, key):
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    if row:
        return row[0]
    return None

@db_operation
def set_setting(conn, cursor, key, value):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))

def do_backup():
    try:
        from backup import GitHubBackup
        GitHubBackup().backup_db()
    except:
        pass

# ===== ЭКСПОРТ =====
__all__ = [
    'init_db', 'migrate_db', '_execute_db',
    'get_user', 'create_user', 'force_create_user',
    'get_tokens', 'add_tokens', 'spend_tokens',
    'get_user_memory', 'init_user_memory', 'update_user_memory',
    'set_user_name',
    'add_to_context',
    'get_last_image', 'get_image_by_id', 'save_image_to_history',
    'get_image_chain_by_session', 'get_edit_version',
    'get_text_requests', 'can_request_text', 'add_text_request',
    'has_trial', 'activate_trial', 'get_trial_remaining',
    'add_referral', 'get_referral_count',
    'use_promocode',
    'create_payment', 'complete_payment',
    'is_admin', 'add_admin',
    'add_premium',
    'block_user', 'unblock_user',
    'get_stats',
    'add_reminder', 'get_due_reminders', 'mark_reminder_sent', 'get_user_reminders', 'delete_reminder',
    'get_setting', 'set_setting',
    'do_backup'
]
