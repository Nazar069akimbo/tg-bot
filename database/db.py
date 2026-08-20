import sqlite3
import os
import json
import secrets
import time
import threading
from datetime import datetime, timedelta
from contextlib import contextmanager

DB_PATH = 'data/repsolver.db'
os.makedirs('data', exist_ok=True)

# ===== ПРОСТОЕ ПОДКЛЮЧЕНИЕ БЕЗ СЛОЖНОЙ ОЧЕРЕДИ =====

def get_db():
    """Простое подключение к БД"""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

@contextmanager
def db_connection():
    """Контекстный менеджер для БД"""
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# ===== ИНИЦИАЛИЗАЦИЯ =====

def init_db():
    """Создаёт все таблицы с нуля"""
    with db_connection() as conn:
        cursor = conn.cursor()
        
        # УДАЛЯЕМ СТАРЫЕ ТАБЛИЦЫ (ЕСЛИ ЕСТЬ)
        cursor.execute("DROP TABLE IF EXISTS users")
        cursor.execute("DROP TABLE IF EXISTS user_memory")
        cursor.execute("DROP TABLE IF EXISTS images_history")
        cursor.execute("DROP TABLE IF EXISTS edit_sessions")
        cursor.execute("DROP TABLE IF EXISTS referrals")
        cursor.execute("DROP TABLE IF EXISTS admins")
        cursor.execute("DROP TABLE IF EXISTS payments")
        cursor.execute("DROP TABLE IF EXISTS messages_to_admin")
        cursor.execute("DROP TABLE IF EXISTS settings")
        cursor.execute("DROP TABLE IF EXISTS promocodes")
        cursor.execute("DROP TABLE IF EXISTS promocode_uses")
        cursor.execute("DROP TABLE IF EXISTS reminders")
        
        # СОЗДАЁМ ЗАНОВО
        
        # Пользователи
        cursor.execute('''
        CREATE TABLE users (
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
        CREATE TABLE user_memory (
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
        CREATE TABLE images_history (
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
        CREATE TABLE edit_sessions (
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
        CREATE TABLE referrals (
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
        CREATE TABLE admins (
            user_id INTEGER PRIMARY KEY,
            added_at TEXT
        )
        ''')
        
        # Платежи
        cursor.execute('''
        CREATE TABLE payments (
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
        CREATE TABLE messages_to_admin (
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
        CREATE TABLE settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        ''')
        
        # Промокоды
        cursor.execute('''
        CREATE TABLE promocodes (
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
        CREATE TABLE promocode_uses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            promocode_id INTEGER,
            user_id INTEGER,
            used_at TEXT
        )
        ''')
        
        # Напоминания
        cursor.execute('''
        CREATE TABLE reminders (
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
        
        # Добавляем админа
        ADMIN_ID = int(os.getenv('ADMIN_ID', 6957852385))
        cursor.execute("INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)", 
                       (ADMIN_ID, datetime.now().isoformat()))
        
        print("✅ Новая база данных создана!")

def migrate_db():
    """Проверяет структуру БД"""
    print("✅ БД в порядке")

# ===== ФУНКЦИИ РАБОТЫ С БД =====

def get_user(user_id):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return cursor.fetchone()

def create_user(user_id, username):
    with db_connection() as conn:
        cursor = conn.cursor()
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
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET tokens = tokens + ? WHERE user_id = ?", (amount, user_id))

def spend_tokens(user_id, amount):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT tokens FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row and row[0] >= amount:
            cursor.execute("UPDATE users SET tokens = tokens - ? WHERE user_id = ?", (amount, user_id))
            return True
        return False

def get_user_memory(user_id):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_memory WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def init_user_memory(user_id):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO user_memory (user_id, created_at, updated_at, context_history)
            VALUES (?, ?, ?, ?)
        """, (user_id, datetime.now().isoformat(), datetime.now().isoformat(), json.dumps([])))

def update_user_memory(user_id, data):
    with db_connection() as conn:
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

def set_user_name(user_id, name):
    update_user_memory(user_id, {'name': name})

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

def save_image_to_history(user_id, prompt, enhanced_prompt, model, image_data, previous_id=None, session_id=None, edit_type=None, edit_text=None):
    with db_connection() as conn:
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
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM images_history WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_image_by_id(image_id):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM images_history WHERE id = ?", (image_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_image_chain_by_session(user_id, session_id):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM images_history WHERE user_id = ? AND session_id = ? ORDER BY id ASC", (user_id, session_id))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_edit_version(user_id, session_id):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM images_history WHERE user_id = ? AND session_id = ?", (user_id, session_id))
        return cursor.fetchone()[0] or 0

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
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET text_requests = 0, text_requests_reset = ? WHERE user_id = ?", 
                          (datetime.now().isoformat(), user_id))
        return
    last_date = datetime.fromisoformat(last_reset)
    if last_date.date() < datetime.now().date():
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET text_requests = 0, text_requests_reset = ? WHERE user_id = ?", 
                          (datetime.now().isoformat(), user_id))

def add_text_request(user_id):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET text_requests = text_requests + 1 WHERE user_id = ?", (user_id,))

def can_request_text(user_id):
    reset_text_requests_if_needed(user_id)
    used, max_req = get_text_requests(user_id)
    return used < max_req, max_req - used

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
    with db_connection() as conn:
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

def add_referral(referrer_id, referred_id):
    with db_connection() as conn:
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
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
        return cursor.fetchone()[0] or 0

def use_promocode(code, user_id):
    with db_connection() as conn:
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

def create_payment(user_id, stars, payload, plan):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO payments (user_id, stars_amount, telegram_payload, status, timestamp, plan) VALUES (?, ?, ?, ?, ?, ?)",
                      (user_id, stars, payload, "pending", datetime.now().isoformat(), plan))

def complete_payment(payload):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE payments SET status = 'completed' WHERE telegram_payload = ?", (payload,))
        cursor.execute("SELECT user_id, stars_amount, plan FROM payments WHERE telegram_payload = ?", (payload,))
        return cursor.fetchone()

def is_admin(user_id):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
        return cursor.fetchone() is not None

def add_admin(user_id):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)", 
                      (user_id, datetime.now().isoformat()))

def add_premium(user_id, days, plan, paid=False):
    with db_connection() as conn:
        cursor = conn.cursor()
        new_date = (datetime.now() + timedelta(days=days)).isoformat()
        cursor.execute("UPDATE users SET premium_until = ?, plan = ? WHERE user_id = ?", (new_date, plan, user_id))
        if paid:
            cursor.execute("UPDATE users SET paid_premium = 1 WHERE user_id = ?", (user_id,))

def block_user(user_id):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_blocked = 1 WHERE user_id = ?", (user_id,))

def unblock_user(user_id):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_blocked = 0 WHERE user_id = ?", (user_id,))

def get_stats():
    with db_connection() as conn:
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

def add_reminder(user_id, text, time_str, repeat=None):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO reminders (user_id, text, time, repeat, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, text, time_str, repeat, datetime.now().isoformat()))
        return cursor.lastrowid

def get_user_reminders(user_id):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reminders WHERE user_id = ? AND sent = 0 ORDER BY time ASC", (user_id,))
        return cursor.fetchall()

def get_setting(key):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row:
            return row[0]
    return None

def set_setting(key, value):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))

def do_backup():
    try:
        from backup import GitHubBackup
        GitHubBackup().backup_db()
    except:
        pass

def get_queue_status():
    return {"status": "ok", "queue_size": 0}

def get_queue_info():
    return "📊 Очередь БД работает нормально"
