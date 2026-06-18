import sqlite3
from datetime import datetime, timedelta
import os

# Путь к БД
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'repsolver.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

def init_db():
    """Инициализация базы данных"""
    # Создаем таблицу users, если её нет
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        joined TEXT,
        premium_until TEXT,
        free_requests INTEGER DEFAULT 0,
        total_requests INTEGER DEFAULT 0,
        is_blocked INTEGER DEFAULT 0,
        mode TEXT DEFAULT 'gdz'
    )
    ''')
    
    # Добавляем колонку referrer_id, если её нет
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN referrer_id INTEGER DEFAULT NULL")
        print("✅ Добавлена колонка referrer_id")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("ℹ️ Колонка referrer_id уже существует")
        else:
            print(f"⚠️ Ошибка при добавлении колонки: {e}")
    
    # Создаем остальные таблицы
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
        timestamp TEXT
    )
    ''')
    conn.commit()
    print("✅ База данных инициализирована")

def init_settings():
    """Инициализация настроек"""
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    ''')
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('free_input_chars', '500')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('free_output_words', '50')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('premium_input_chars', '3000')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('premium_output_words', '300')")
    conn.commit()
    print("✅ Настройки инициализированы")

def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return cursor.fetchone()

def create_user(user_id, username, referrer_id=None):
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, joined, referrer_id) VALUES (?, ?, ?, ?)",
                   (user_id, username, datetime.now().isoformat(), referrer_id))
    conn.commit()

def is_admin(user_id):
    cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    return cursor.fetchone() is not None

def add_admin(user_id):
    cursor.execute("INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)", 
                   (user_id, datetime.now().isoformat()))
    conn.commit()

def is_premium(user_id):
    user = get_user(user_id)
    if not user or not user[3]:
        return False
    return datetime.now().isoformat() < user[3]

def add_premium(user_id, days):
    new_date = (datetime.now() + timedelta(days=days)).isoformat()
    cursor.execute("UPDATE users SET premium_until = ? WHERE user_id = ?", (new_date, user_id))
    conn.commit()

def can_request(user_id):
    user = get_user(user_id)
    if not user:
        return True, 10
    if user[3] and datetime.now().isoformat() < user[3]:
        return True, 999999
    used = user[4] or 0
    free_limit = 10
    return used < free_limit, free_limit - used

def add_request(user_id):
    cursor.execute("UPDATE users SET free_requests = free_requests + 1, total_requests = total_requests + 1 WHERE user_id = ?", (user_id,))
    conn.commit()

def set_mode(user_id, mode):
    cursor.execute("UPDATE users SET mode = ? WHERE user_id = ?", (mode, user_id))
    conn.commit()

def get_mode(user_id):
    user = get_user(user_id)
    return user[7] if user and user[7] else "gdz"

def get_setting(key):
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    result = cursor.fetchone()
    if result:
        return result[0]
    return '0'

def set_setting(key, value):
    cursor.execute("UPDATE settings SET value = ? WHERE key = ?", (value, key))
    conn.commit()

def get_stats():
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE premium_until IS NOT NULL AND premium_until > datetime('now')")
    premium_users = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(total_requests) FROM users")
    total_requests = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 1")
    blocked_users = cursor.fetchone()[0]
    return total_users, premium_users, total_requests, blocked_users
