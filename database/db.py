import sqlite3, os
from datetime import datetime, timedelta

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
        mode TEXT DEFAULT "chat",
        image_requests INTEGER DEFAULT 0,
        plan TEXT DEFAULT "basic",
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
    
    default_settings = [
        ('free_input_chars', '500'),
        ('free_output_words', '50'),
        ('premium_input_chars', '3000'),
        ('premium_output_words', '300'),
        ('premium_deluxe_input_chars', '5000'),
        ('premium_deluxe_output_words', '500'),
        ('image_limit_free', '3'),
        ('image_limit_premium', '50'),
        ('image_limit_premium_deluxe', '200')
    ]
    
    for key, value in default_settings:
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
    
    conn.commit()
    print("✅ База данных инициализирована")

def get_user(user_id):
    try:
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return cursor.fetchone()
    except Exception as e:
        print(f"⚠️ Ошибка get_user: {e}")
        return None

def create_user(user_id, username):
    try:
        now = datetime.now().isoformat()
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if cursor.fetchone():
            print(f"ℹ️ Пользователь {user_id} уже существует")
            return True
        cursor.execute("""
            INSERT INTO users 
            (user_id, username, joined, trial_start, trial_active, last_image_reset) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, username, now, now, 1, now))
        conn.commit()
        print(f"✅ Создан пользователь {user_id}")
        return True
    except Exception as e:
        print(f"❌ Ошибка create_user: {e}")
        return False

def add_referral(referrer_id, referred_id):
    try:
        cursor.execute("INSERT INTO referrals (referrer_id, referred_id, joined) VALUES (?, ?, ?)",
                    (referrer_id, referred_id, datetime.now().isoformat()))
        conn.commit()
        cursor.execute("UPDATE users SET free_requests = free_requests + 5 WHERE user_id = ?", (referrer_id,))
        conn.commit()
        print(f"✅ Реферал: {referrer_id} <- {referred_id}")
        return True
    except Exception as e:
        print(f"⚠️ Ошибка add_referral: {e}")
        return False

def is_admin(user_id):
    try:
        cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
        return cursor.fetchone() is not None
    except:
        return False

def add_admin(user_id):
    try:
        cursor.execute("INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)", (user_id, datetime.now().isoformat()))
        conn.commit()
        return True
    except:
        return False

def is_premium(user_id):
    try:
        user = get_user(user_id)
        if not user: return False
        premium_until = user[3] if len(user) > 3 else None
        return premium_until and datetime.now().isoformat() < premium_until
    except:
        return False

def get_user_plan(user_id):
    user = get_user(user_id)
    if user and len(user) > 9:
        plan = user[9]
        if plan in ['premium', 'premium_deluxe']:
            return plan
    return 'basic'

def set_user_plan(user_id, plan):
    try:
        cursor.execute("UPDATE users SET plan = ? WHERE user_id = ?", (plan, user_id))
        conn.commit()
        return True
    except:
        return False

def add_premium(user_id, days, plan='premium'):
    try:
        new_date = (datetime.now() + timedelta(days=days)).isoformat()
        cursor.execute("UPDATE users SET premium_until = ?, plan = ? WHERE user_id = ?",
                    (new_date, plan, user_id))
        conn.commit()
        print(f"✅ Выдан {plan} на {days} дней для {user_id}")
        return True
    except Exception as e:
        print(f"⚠️ Ошибка add_premium: {e}")
        return False

def remove_premium(user_id):
    try:
        cursor.execute("UPDATE users SET premium_until = NULL, plan = 'basic' WHERE user_id = ?", (user_id,))
        conn.commit()
        return True
    except:
        return False

def block_user(user_id):
    try:
        cursor.execute("UPDATE users SET is_blocked = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        return True
    except:
        return False

def unblock_user(user_id):
    try:
        cursor.execute("UPDATE users SET is_blocked = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
        return True
    except:
        return False

def can_request(user_id):
    try:
        user = get_user(user_id)
        if not user: return True, 10
        if is_premium(user_id): return True, 999999
        used = user[4] if len(user) > 4 and user[4] else 0
        used = int(used) if used else 0
        return used < 10, 10 - used
    except:
        return True, 10

def add_request(user_id):
    try:
        cursor.execute("UPDATE users SET free_requests = free_requests + 1, total_requests = total_requests + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        return True
    except:
        return False

def get_setting(key):
    try:
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        r = cursor.fetchone()
        if r: return r[0]
    except:
        pass
    defaults = {
        'free_input_chars': '500',
        'free_output_words': '50',
        'premium_input_chars': '3000',
        'premium_output_words': '300',
        'premium_deluxe_input_chars': '5000',
        'premium_deluxe_output_words': '500',
        'image_limit_free': '3',
        'image_limit_premium': '50',
        'image_limit_premium_deluxe': '200'
    }
    return defaults.get(key, '0')

def set_setting(key, value):
    try:
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        return True
    except:
        return False

def reset_image_count_if_needed(user_id):
    try:
        user = get_user(user_id)
        if not user or len(user) < 14: return
        last_reset = user[13] if len(user) > 13 else None
        if not last_reset:
            cursor.execute("UPDATE users SET last_image_reset = ? WHERE user_id = ?", (datetime.now().isoformat(), user_id))
            conn.commit()
            return
        if last_reset:
            last_date = datetime.fromisoformat(last_reset)
            today = datetime.now()
            if last_date.date() < today.date():
                cursor.execute("UPDATE users SET image_requests = 0, last_image_reset = ? WHERE user_id = ?", 
                              (today.isoformat(), user_id))
                conn.commit()
    except:
        pass

def get_image_limit(user_id):
    plan = get_user_plan(user_id)
    if plan == 'premium_deluxe':
        return int(get_setting('image_limit_premium_deluxe') or 200)
    elif plan == 'premium':
        return int(get_setting('image_limit_premium') or 50)
    else:
        return int(get_setting('image_limit_free') or 3)

def can_generate_image(user_id):
    try:
        reset_image_count_if_needed(user_id)
        user = get_user(user_id)
        if not user: return True, 3
        used = user[8] if len(user) > 8 and user[8] else 0
        used = int(used) if used else 0
        limit = get_image_limit(user_id)
        return used < limit, limit - used
    except:
        return True, 3

def get_image_stats(user_id):
    try:
        reset_image_count_if_needed(user_id)
        user = get_user(user_id)
        if not user: return 0, 3, False, 'basic'
        used = user[8] if len(user) > 8 and user[8] else 0
        used = int(used) if used else 0
        limit = get_image_limit(user_id)
        prem = is_premium(user_id)
        plan = get_user_plan(user_id)
        return used, limit, prem, plan
    except:
        return 0, 3, False, 'basic'

def add_image_request(user_id):
    try:
        cursor.execute("UPDATE users SET image_requests = image_requests + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        return True
    except:
        return False

def get_stats():
    try:
        cursor.execute("SELECT COUNT(*) FROM users")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE premium_until > datetime('now')")
        prem = cursor.fetchone()[0]
        cursor.execute("SELECT SUM(total_requests) FROM users")
        req = cursor.fetchone()[0] or 0
        return total, prem, req
    except:
        return 0, 0, 0

def is_trial_active(user_id):
    try:
        user = get_user(user_id)
        if not user or len(user) < 11: return False
        trial_start = user[10] if len(user) > 10 else None
        if not trial_start: return False
        start_date = datetime.fromisoformat(trial_start)
        return (datetime.now() - start_date).days < 2
    except:
        return False

def get_trial_remaining(user_id):
    if not is_trial_active(user_id): return 0
    user = get_user(user_id)
    if not user or len(user) < 12: return 0
    trial_used = user[11] if user[11] else 0
    trial_used = int(trial_used) if trial_used else 0
    return max(0, 5 - trial_used)

def use_trial_image(user_id):
    try:
        cursor.execute("UPDATE users SET trial_used = trial_used + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        return True
    except:
        return False

def get_mode(user_id):
    user = get_user(user_id)
    return user[7] if user and len(user) > 7 and user[7] else "chat"
