import sqlite3
import os
import json
import secrets
import time
import threading
from datetime import datetime, timedelta
from contextlib import contextmanager
from functools import lru_cache

DB_PATH = 'data/repsolver.db'
os.makedirs('data', exist_ok=True)

# === НАСТРОЙКИ ===
SQLITE_TIMEOUT = 60
SQLITE_RETRY_COUNT = 5
SQLITE_RETRY_DELAY = 0.5

# === ЛОКАЛЬНЫЙ ПУЛ СОЕДИНЕНИЙ (ДЛЯ ПОТОКОВ) ===
_thread_local = threading.local()

def get_connection():
    """Получить соединение из пула для текущего потока"""
    if not hasattr(_thread_local, 'conn') or _thread_local.conn is None:
        _thread_local.conn = sqlite3.connect(DB_PATH, timeout=SQLITE_TIMEOUT)
        _thread_local.conn.row_factory = sqlite3.Row
        # Настройки для производительности
        _thread_local.conn.execute("PRAGMA journal_mode=WAL")
        _thread_local.conn.execute("PRAGMA synchronous=NORMAL")
        _thread_local.conn.execute("PRAGMA cache_size=10000")
        _thread_local.conn.execute("PRAGMA temp_store=MEMORY")
    return _thread_local.conn

def close_connection():
    """Закрыть соединение для текущего потока"""
    if hasattr(_thread_local, 'conn') and _thread_local.conn:
        try:
            _thread_local.conn.close()
        except:
            pass
        _thread_local.conn = None

@contextmanager
def get_db():
    """Подключение к БД с повторными попытками при блокировке"""
    last_error = None
    conn = None
    
    for attempt in range(SQLITE_RETRY_COUNT):
        try:
            # Пробуем взять из пула
            conn = get_connection()
            yield conn
            conn.commit()
            return
            
        except sqlite3.OperationalError as e:
            last_error = e
            if "database is locked" in str(e):
                # Закрываем соединение и пробуем заново
                close_connection()
                time.sleep(SQLITE_RETRY_DELAY * (attempt + 1))
                continue
            raise
            
        except Exception as e:
            last_error = e
            raise
            
        finally:
            # Закрываем соединение только если это был последний вызов
            if attempt == SQLITE_RETRY_COUNT - 1:
                close_connection()
    
    if last_error:
        raise last_error

# === ОБЁРТКА ДЛЯ ЗАПРОСОВ С КЭШИРОВАНИЕМ ===
@lru_cache(maxsize=128)
def get_cached_user(user_id):
    """Кэшированный запрос пользователя"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return cursor.fetchone()

def invalidate_user_cache(user_id):
    """Очистить кэш для пользователя"""
    get_cached_user.cache_clear()

# === ИНИЦИАЛИЗАЦИЯ ===
def init_db():
    """Инициализация БД со всеми таблицами"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Пользователи
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
        
        # Память
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
        
        # История картинок
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
        
        # Сессии правок
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
        
        # Рефералы
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
        
        # Админы
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            added_at TEXT
        )
        ''')
        
        # Платежи
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
        
        # Сообщения
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
        
        # Настройки
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        ''')
        
        # Промокоды
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
        
        # Напоминания
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
        
        # Настройки по умолчанию
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
        
        # Админ
        ADMIN_ID = int(os.getenv('ADMIN_ID', 6957852385))
        cursor.execute("INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)", 
                       (ADMIN_ID, datetime.now().isoformat()))
        
        print("✅ База данных инициализирована")

def migrate_db():
    """Автоматическая миграция"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Проверяем promocodes
            cursor.execute("PRAGMA table_info(promocodes)")
            cols = [row[1] for row in cursor.fetchall()]
            
            for col in ['bonus_tokens', 'bonus_images', 'bonus_requests', 'max_uses', 'used']:
                if col not in cols:
                    cursor.execute(f"ALTER TABLE promocodes ADD COLUMN {col} INTEGER DEFAULT 0")
                    print(f"✅ Добавлена {col}")
            
            print("✅ Миграция выполнена")
    except Exception as e:
        print(f"⚠️ Ошибка миграции: {e}")

# ===== ОСНОВНЫЕ ФУНКЦИИ =====

def get_user(user_id):
    """Получить пользователя (с кэшированием)"""
    return get_cached_user(user_id)

def create_user(user_id, username):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if cursor.fetchone():
            return True
        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO users (user_id, username, joined, trial_start, trial_active, last_image_reset)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, username, now, now, 1, now))
        invalidate_user_cache(user_id)
        return True

def force_create_user(user_id, username=None):
    try:
        user = get_user(user_id)
        if user:
            return user
        create_user(user_id, username or str(user_id))
        init_user_memory(user_id)
        return get_user(user_id)
    except:
        return None

def get_tokens(user_id):
    user = get_user(user_id)
    if not user:
        return 0
    return user['tokens'] if user['tokens'] else 0

def add_tokens(user_id, amount):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET tokens = tokens + ? WHERE user_id = ?", (amount, user_id))
        invalidate_user_cache(user_id)

def spend_tokens(user_id, amount):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT tokens FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row and row[0] >= amount:
            cursor.execute("UPDATE users SET tokens = tokens - ? WHERE user_id = ?", (amount, user_id))
            invalidate_user_cache(user_id)
            return True
        return False

# ===== ПАМЯТЬ =====

def get_user_memory(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_memory WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def init_user_memory(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO user_memory (user_id, created_at, updated_at, context_history)
            VALUES (?, ?, ?, ?)
        """, (user_id, datetime.now().isoformat(), datetime.now().isoformat(), json.dumps([])))

def update_user_memory(user_id, data):
    with get_db() as conn:
        cursor = conn.cursor()
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

# ===== ИСТОРИЯ КАРТИНОК =====

def save_image_to_history(user_id, prompt, enhanced_prompt, model, image_data, previous_id=None, session_id=None, edit_type=None, edit_text=None):
    with get_db() as conn:
        cursor = conn.cursor()
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

def get_last_image(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM images_history WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_image_by_id(image_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM images_history WHERE id = ?", (image_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_image_chain_by_session(user_id, session_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM images_history WHERE user_id = ? AND session_id = ? ORDER BY id ASC", (user_id, session_id))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_edit_version(user_id, session_id):
    chain = get_image_chain_by_session(user_id, session_id)
    return len(chain)

# ===== ТЕКСТ =====

def get_text_requests(user_id):
    user = get_user(user_id)
    if not user:
        return 0, 10
    used = user['text_requests'] if user['text_requests'] else 0
    max_req = user['max_text_requests'] if user['max_text_requests'] else 10
    return used, max_req

def reset_text_requests_if_needed(user_id):
    user = get_user(user_id)
    if not user:
        return
    last_reset = user['text_requests_reset'] if user['text_requests_reset'] else None
    if not last_reset:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET text_requests = 0, text_requests_reset = ? WHERE user_id = ?", 
                          (datetime.now().isoformat(), user_id))
        return
    last_date = datetime.fromisoformat(last_reset)
    if last_date.date() < datetime.now().date():
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET text_requests = 0, text_requests_reset = ? WHERE user_id = ?", 
                          (datetime.now().isoformat(), user_id))

def add_text_request(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET text_requests = text_requests + 1 WHERE user_id = ?", (user_id,))

def can_request_text(user_id):
    reset_text_requests_if_needed(user_id)
    used, max_req = get_text_requests(user_id)
    return used < max_req, max_req - used

# ===== ТРИАЛ =====

def has_trial(user_id):
    user = get_user(user_id)
    if not user:
        return False
    trial_start = user['trial_start'] if user['trial_start'] else None
    if not trial_start:
        return False
    start_date = datetime.fromisoformat(trial_start)
    return (datetime.now() - start_date).days < 3

def activate_trial(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET trial_start = ?, tokens = tokens + 20 WHERE user_id = ?", 
                      (datetime.now().isoformat(), user_id))

def get_trial_remaining(user_id):
    user = get_user(user_id)
    if not user:
        return 0
    trial_start = user['trial_start'] if user['trial_start'] else None
    if not trial_start:
        return 0
    start_date = datetime.fromisoformat(trial_start)
    days_passed = (datetime.now() - start_date).days
    return max(0, 3 - days_passed)

# ===== РЕФЕРАЛЫ =====

def add_referral(referrer_id, referred_id):
    with get_db() as conn:
        cursor = conn.cursor()
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

def get_referral_count(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
        return cursor.fetchone()[0] or 0

# ===== ПРОМОКОДЫ =====

def use_promocode(code, user_id):
    with get_db() as conn:
        cursor = conn.cursor()
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

# ===== ПЛАТЕЖИ =====

def create_payment(user_id, stars, payload, plan):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO payments (user_id, stars_amount, telegram_payload, status, timestamp, plan) VALUES (?, ?, ?, ?, ?, ?)",
                      (user_id, stars, payload, "pending", datetime.now().isoformat(), plan))

def complete_payment(payload):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE payments SET status = 'completed' WHERE telegram_payload = ?", (payload,))
        cursor.execute("SELECT user_id, stars_amount, plan FROM payments WHERE telegram_payload = ?", (payload,))
        return cursor.fetchone()

# ===== АДМИНЫ =====

def is_admin(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
        return cursor.fetchone() is not None

def add_admin(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)", 
                      (user_id, datetime.now().isoformat()))

# ===== ПРЕМИУМ =====

def add_premium(user_id, days, plan, paid=False):
    with get_db() as conn:
        cursor = conn.cursor()
        new_date = (datetime.now() + timedelta(days=days)).isoformat()
        cursor.execute("UPDATE users SET premium_until = ?, plan = ? WHERE user_id = ?", (new_date, plan, user_id))
        if paid:
            cursor.execute("UPDATE users SET paid_premium = 1 WHERE user_id = ?", (user_id,))
        invalidate_user_cache(user_id)

# ===== БЛОКИРОВКА =====

def block_user(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_blocked = 1 WHERE user_id = ?", (user_id,))
        invalidate_user_cache(user_id)

def unblock_user(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_blocked = 0 WHERE user_id = ?", (user_id,))
        invalidate_user_cache(user_id)

# ===== СТАТИСТИКА =====

def get_stats():
    with get_db() as conn:
        cursor = conn.cursor()
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

# ===== НАПОМИНАНИЯ =====

def add_reminder(user_id, text, time_str, repeat=None):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO reminders (user_id, text, time, repeat, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, text, time_str, repeat, datetime.now().isoformat()))
        return cursor.lastrowid

def get_due_reminders():
    with get_db() as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute("SELECT * FROM reminders WHERE sent = 0 AND time <= ? ORDER BY time ASC", (now,))
        return cursor.fetchall()

def mark_reminder_sent(reminder_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (reminder_id,))

def get_user_reminders(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reminders WHERE user_id = ? AND sent = 0 ORDER BY time ASC", (user_id,))
        return cursor.fetchall()

def delete_reminder(reminder_id, user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reminders WHERE id = ? AND user_id = ?", (reminder_id, user_id))

# ===== ВСПОМОГАТЕЛЬНЫЕ =====

def do_backup():
    try:
        from backup import GitHubBackup
        GitHubBackup().backup_db()
    except:
        pass

def get_setting(key):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row:
            return row[0]
    return None

def set_setting(key, value):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
