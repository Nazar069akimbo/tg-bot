import sqlite3, os
from datetime import datetime, timedelta

DB_PATH = 'data/repsolver.db'
os.makedirs('data', exist_ok=True)
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

def init_db():
    # Проверяем существование таблицы users
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    table_exists = cursor.fetchone()
    
    if not table_exists:
        # Создаём таблицу с нуля
        cursor.execute('''
        CREATE TABLE users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            joined TEXT,
            premium_until TEXT,
            free_requests INTEGER DEFAULT 0,
            total_requests INTEGER DEFAULT 0,
            is_blocked INTEGER DEFAULT 0,
            mode TEXT DEFAULT "chat",
            image_requests INTEGER DEFAULT 0,
            plan TEXT DEFAULT "basic",
            trial_start TEXT,
            trial_used INTEGER DEFAULT 0,
            trial_active INTEGER DEFAULT 0,
            last_image_reset TEXT
        )
        ''')
        print("✅ Создана таблица users")
    else:
        # Проверяем и добавляем недостающие колонки
        cursor.execute("PRAGMA table_info(users)")
        existing_cols = [row[1] for row in cursor.fetchall()]
        
        columns_to_add = {
            'image_requests': 'INTEGER DEFAULT 0',
            'plan': 'TEXT DEFAULT "basic"',
            'trial_start': 'TEXT',
            'trial_used': 'INTEGER DEFAULT 0',
            'trial_active': 'INTEGER DEFAULT 0',
            'last_image_reset': 'TEXT'
        }
        
        for col, dtype in columns_to_add.items():
            if col not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {dtype}")
                    print(f"✅ Добавлена колонка {col}")
                except Exception as e:
                    print(f"⚠️ Ошибка добавления {col}: {e}")
    
    # Остальные таблицы
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
        status TEXT DEFAULT "new"
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    ''')
    
    # Настройки по умолчанию
    default_settings = [
        ('free_input_chars', '500'),
        ('free_output_words', '50'),
        ('premium_input_chars', '3000'),
        ('premium_output_words', '300'),
        ('image_limit_free', '3'),
        ('image_limit_premium', '50')
    ]
    
    for key, value in default_settings:
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
    
    conn.commit()
    print("✅ База данных инициализирована")

def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return cursor.fetchone()

def create_user(user_id, username):
    now = datetime.now().isoformat()
    # Проверяем существование колонок
    cursor.execute("PRAGMA table_info(users)")
    cols = [row[1] for row in cursor.fetchall()]
    
    if 'last_image_reset' in cols:
        cursor.execute("""
            INSERT OR IGNORE INTO users 
            (user_id, username, joined, trial_start, trial_active, last_image_reset) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, username, now, now, 1, now))
    else:
        cursor.execute("""
            INSERT OR IGNORE INTO users 
            (user_id, username, joined) 
            VALUES (?, ?, ?)
        """, (user_id, username, now))
    conn.commit()

def add_referral(referrer_id, referred_id):
    cursor.execute("INSERT INTO referrals (referrer_id, referred_id, joined) VALUES (?, ?, ?)",
                (referrer_id, referred_id, datetime.now().isoformat()))
    conn.commit()
    cursor.execute("UPDATE users SET free_requests = free_requests + 5 WHERE user_id = ?", (referrer_id,))
    conn.commit()

def is_admin(user_id):
    cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    return cursor.fetchone() is not None

def add_admin(user_id):
    cursor.execute("INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)", (user_id, datetime.now().isoformat()))
    conn.commit()

def is_premium(user_id):
    user = get_user(user_id)
    if not user:
        return False
    premium_until = user[3] if len(user) > 3 else None
    return premium_until and datetime.now().isoformat() < premium_until

def add_premium(user_id, days):
    cursor.execute("UPDATE users SET premium_until = ?, plan = 'premium' WHERE user_id = ?",
                ((datetime.now() + timedelta(days=days)).isoformat(), user_id))
    conn.commit()

def can_request(user_id):
    user = get_user(user_id)
    if not user: return True, 10
    if is_premium(user_id): return True, 999999
    used = user[4] if len(user) > 4 and user[4] else 0
    try:
        used = int(used)
    except:
        used = 0
    return used < 10, 10 - used

def add_request(user_id):
    cursor.execute("UPDATE users SET free_requests = free_requests + 1, total_requests = total_requests + 1 WHERE user_id = ?", (user_id,))
    conn.commit()

def get_setting(key):
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    r = cursor.fetchone()
    if r:
        return r[0]
    defaults = {
        'free_input_chars': '500',
        'free_output_words': '50',
        'premium_input_chars': '3000',
        'premium_output_words': '300',
        'image_limit_free': '3',
        'image_limit_premium': '50'
    }
    return defaults.get(key, '0')

def set_setting(key, value):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()

def reset_image_count_if_needed(user_id):
    try:
        user = get_user(user_id)
        if not user:
            return
        
        # Проверяем наличие колонок
        if len(user) < 14:
            return
        
        last_reset = user[13] if len(user) > 13 else None
        if not last_reset:
            try:
                cursor.execute("UPDATE users SET last_image_reset = ? WHERE user_id = ?", (datetime.now().isoformat(), user_id))
                conn.commit()
            except:
                pass
            return
        
        if last_reset:
            try:
                last_date = datetime.fromisoformat(last_reset)
                today = datetime.now()
                if last_date.date() < today.date():
                    cursor.execute("UPDATE users SET image_requests = 0, last_image_reset = ? WHERE user_id = ?", 
                                  (today.isoformat(), user_id))
                    conn.commit()
            except:
                pass
    except Exception as e:
        print(f"⚠️ Ошибка сброса счётчика: {e}")

def get_image_limit(user_id):
    if is_premium(user_id):
        val = get_setting('image_limit_premium')
        return int(val) if val else 50
    val = get_setting('image_limit_free')
    return int(val) if val else 3

def can_generate_image(user_id):
    try:
        reset_image_count_if_needed(user_id)
        user = get_user(user_id)
        if not user: return True, 3
        
        # Безопасное получение значения
        used = 0
        if len(user) > 8 and user[8]:
            try:
                used = int(user[8])
            except:
                used = 0
        
        limit = get_image_limit(user_id)
        return used < limit, limit - used
    except Exception as e:
        print(f"⚠️ Ошибка can_generate_image: {e}")
        return True, 3

def get_image_stats(user_id):
    try:
        reset_image_count_if_needed(user_id)
        user = get_user(user_id)
        if not user: return 0, 3, False
        
        used = 0
        if len(user) > 8 and user[8]:
            try:
                used = int(user[8])
            except:
                used = 0
        
        limit = get_image_limit(user_id)
        prem = is_premium(user_id)
        return used, limit, prem
    except Exception as e:
        print(f"⚠️ Ошибка get_image_stats: {e}")
        return 0, 3, False

def add_image_request(user_id):
    try:
        cursor.execute("UPDATE users SET image_requests = image_requests + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
    except Exception as e:
        print(f"⚠️ Ошибка add_image_request: {e}")

def get_stats():
    cursor.execute("SELECT COUNT(*) FROM users"); total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE premium_until > datetime('now')"); prem = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(total_requests) FROM users"); req = cursor.fetchone()[0] or 0
    return total, prem, req

def get_user_plan(user_id):
    user = get_user(user_id)
    return user[9] if user and len(user) > 9 and user[9] else 'basic'

def set_user_plan(user_id, plan):
    cursor.execute("UPDATE users SET plan = ? WHERE user_id = ?", (plan, user_id))
    conn.commit()

def is_trial_active(user_id):
    user = get_user(user_id)
    if not user or len(user) < 12 or not user[11]:
        return False
    try:
        trial_start = user[9] if len(user) > 9 else None
        if not trial_start:
            return False
        return (datetime.now() - datetime.fromisoformat(trial_start)).days < 2
    except:
        return False

def get_trial_remaining(user_id):
    if not is_trial_active(user_id):
        return 0
    user = get_user(user_id)
    if not user:
        return 0
    trial_used = user[10] if len(user) > 10 and user[10] else 0
    try:
        trial_used = int(trial_used)
    except:
        trial_used = 0
    return max(0, 5 - trial_used)

def use_trial_image(user_id):
    cursor.execute("UPDATE users SET trial_used = trial_used + 1 WHERE user_id = ?", (user_id,))
    conn.commit()

def get_mode(user_id):
    user = get_user(user_id)
    return user[7] if user and len(user) > 7 and user[7] else "chat"
