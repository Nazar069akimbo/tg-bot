import sqlite3
from datetime import datetime, timedelta
import os

DB_PATH = 'data/repsolver.db'
os.makedirs('data', exist_ok=True)

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

def init_db():
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        joined TEXT,
        premium_until TEXT,
        free_requests INTEGER DEFAULT 0,
        total_requests INTEGER DEFAULT 0,
        is_blocked INTEGER DEFAULT 0,
        mode TEXT DEFAULT 'chat',
        image_requests INTEGER DEFAULT 0,
        image_limit INTEGER DEFAULT 3,
        plan TEXT DEFAULT 'basic',
        user_mode TEXT DEFAULT 'text',
        trial_start TEXT,
        trial_used INTEGER DEFAULT 0,
        trial_active INTEGER DEFAULT 0,
        last_image_reset TEXT
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id INTEGER,
        referred_id INTEGER,
        joined TEXT,
        bonus_given INTEGER DEFAULT 0
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
        timestamp TEXT
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages_to_admin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        text TEXT,
        date TEXT,
        status TEXT DEFAULT 'new'
    )
    ''')
    
    # Добавляем колонки если их нет
    for col in ['image_requests', 'image_limit', 'plan', 'user_mode', 'trial_start', 'trial_used', 'trial_active', 'last_image_reset']:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} DEFAULT '0'")
        except sqlite3.OperationalError:
            pass
    
    conn.commit()
    print("✅ База данных готова")

def init_settings():
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
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('image_limit_free', '3')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('image_limit_premium', '50')")
    conn.commit()
    print("✅ Настройки инициализированы")

def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return cursor.fetchone()

def create_user(user_id, username):
    now = datetime.now().isoformat()
    cursor.execute("""
        INSERT OR IGNORE INTO users 
        (user_id, username, joined, trial_start, trial_active, last_image_reset) 
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, username, now, now, 1, now))
    conn.commit()

def add_referral(referrer_id, referred_id):
    try:
        cursor.execute("INSERT INTO referrals (referrer_id, referred_id, joined) VALUES (?, ?, ?)",
                       (referrer_id, referred_id, datetime.now().isoformat()))
        conn.commit()
        cursor.execute("UPDATE users SET free_requests = free_requests + 5 WHERE user_id = ?", (referrer_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error adding referral: {e}")
        return False

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
    cursor.execute("UPDATE users SET plan = 'premium' WHERE user_id = ?", (user_id,))
    conn.commit()

# ============ ТЕКСТОВЫЕ ЗАПРОСЫ ============
def can_request(user_id):
    user = get_user(user_id)
    if not user:
        return True, 10
    # Premium - безлимит
    if user[3] and datetime.now().isoformat() < user[3]:
        return True, 999999
    used = user[4] or 0
    free_limit = 10
    return used < free_limit, free_limit - used

def add_request(user_id):
    cursor.execute("UPDATE users SET free_requests = free_requests + 1, total_requests = total_requests + 1 WHERE user_id = ?", (user_id,))
    conn.commit()

# ============ КАРТИНКИ ============
def reset_image_count_if_needed(user_id):
    """Сбрасывает счётчик картинок если прошёл день"""
    user = get_user(user_id)
    if not user:
        return
    
    last_reset = user[13] if len(user) > 13 else None
    if not last_reset:
        # Если нет даты сброса - устанавливаем
        cursor.execute("UPDATE users SET last_image_reset = ? WHERE user_id = ?", 
                      (datetime.now().isoformat(), user_id))
        conn.commit()
        return
    
    try:
        last_date = datetime.fromisoformat(last_reset)
        today = datetime.now()
        
        # Если прошёл день - сбрасываем счётчик
        if last_date.date() < today.date():
            cursor.execute("UPDATE users SET image_requests = 0, last_image_reset = ? WHERE user_id = ?", 
                          (today.isoformat(), user_id))
            conn.commit()
            print(f"🔄 Сброшен счётчик картинок для {user_id}")
    except:
        pass

def get_image_limit(user_id):
    """Получить лимит картинок для пользователя"""
    user = get_user(user_id)
    if not user:
        return 3
    
    # Premium пользователи
    if user[3] and datetime.now().isoformat() < user[3]:
        return int(get_setting('image_limit_premium') or 50)
    
    # Обычные пользователи
    return int(get_setting('image_limit_free') or 3)

def can_generate_image(user_id):
    """Проверяет может ли пользователь генерировать картинку"""
    user = get_user(user_id)
    if not user:
        return True, 3
    
    # Сбрасываем счётчик если прошёл день
    reset_image_count_if_needed(user_id)
    
    # Проверяем лимит
    limit = get_image_limit(user_id)
    used = user[8] if len(user) > 8 else 0
    
    # Premium - больше лимит
    if user[3] and datetime.now().isoformat() < user[3]:
        limit = int(get_setting('image_limit_premium') or 50)
        remaining = limit - used
        return used < limit, remaining
    
    # Обычные пользователи - 3 картинки в день
    remaining = limit - used
    return used < limit, remaining

def add_image_request(user_id):
    """Увеличивает счётчик использованных картинок"""
    cursor.execute("UPDATE users SET image_requests = image_requests + 1 WHERE user_id = ?", (user_id,))
    conn.commit()

def get_image_stats(user_id):
    """Получить статистику по картинкам"""
    user = get_user(user_id)
    if not user:
        return 0, 3, False
    
    reset_image_count_if_needed(user_id)
    
    used = user[8] if len(user) > 8 else 0
    limit = get_image_limit(user_id)
    is_prem = user[3] and datetime.now().isoformat() < user[3]
    
    return used, limit, is_prem

def set_mode(user_id, mode):
    cursor.execute("UPDATE users SET mode = ? WHERE user_id = ?", (mode, user_id))
    conn.commit()

def get_mode(user_id):
    user = get_user(user_id)
    return user[7] if user and user[7] else "chat"

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

def get_user_plan(user_id):
    user = get_user(user_id)
    if user and len(user) > 9:
        return user[9]
    return 'basic'

def set_user_plan(user_id, plan):
    cursor.execute("UPDATE users SET plan = ? WHERE user_id = ?", (plan, user_id))
    conn.commit()

def get_user_mode(user_id):
    user = get_user(user_id)
    if user and len(user) > 11:
        return user[11]
    return 'text'

def set_user_mode(user_id, mode):
    cursor.execute("UPDATE users SET user_mode = ? WHERE user_id = ?", (mode, user_id))
    conn.commit()

def get_trial_info(user_id):
    user = get_user(user_id)
    if not user or len(user) < 12:
        return None, 0, False
    trial_start = user[9] if len(user) > 9 else None
    trial_used = user[10] if len(user) > 10 else 0
    trial_active = user[11] if len(user) > 11 else 0
    return trial_start, trial_used, bool(trial_active)

def is_trial_active(user_id):
    trial_start, trial_used, trial_active = get_trial_info(user_id)
    if not trial_active or not trial_start:
        return False
    start_date = datetime.fromisoformat(trial_start)
    days_passed = (datetime.now() - start_date).days
    return days_passed < 2

def get_trial_remaining(user_id):
    if not is_trial_active(user_id):
        return 0
    _, trial_used, _ = get_trial_info(user_id)
    trial_limit = 5
    return max(0, trial_limit - trial_used)

def use_trial_image(user_id):
    cursor.execute("UPDATE users SET trial_used = trial_used + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
