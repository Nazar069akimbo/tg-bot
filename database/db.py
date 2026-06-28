import sqlite3, os
from datetime import datetime, timedelta

DB_PATH = 'data/repsolver.db'
os.makedirs('data', exist_ok=True)
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

def init_db():
    tables = {
        'users': 'user_id INTEGER PRIMARY KEY, username TEXT, joined TEXT, premium_until TEXT, free_requests INTEGER DEFAULT 0, total_requests INTEGER DEFAULT 0, is_blocked INTEGER DEFAULT 0, mode TEXT DEFAULT "chat", image_requests INTEGER DEFAULT 0, plan TEXT DEFAULT "basic", trial_start TEXT, trial_used INTEGER DEFAULT 0, trial_active INTEGER DEFAULT 0, last_image_reset TEXT',
        'referrals': 'id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER, referred_id INTEGER, joined TEXT, bonus_given INTEGER DEFAULT 0',
        'admins': 'user_id INTEGER PRIMARY KEY, added_at TEXT',
        'payments': 'id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, stars_amount INTEGER, telegram_payload TEXT, status TEXT, timestamp TEXT',
        'messages_to_admin': 'id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, text TEXT, date TEXT, status TEXT DEFAULT "new"',
        'settings': 'key TEXT PRIMARY KEY, value TEXT'
    }
    for name, schema in tables.items():
        cursor.execute(f"CREATE TABLE IF NOT EXISTS {name} ({schema})")
    
    for col, dtype in [('image_requests', 'INTEGER DEFAULT 0'), ('plan', 'TEXT DEFAULT "basic"'), ('trial_start', 'TEXT'), ('trial_used', 'INTEGER DEFAULT 0'), ('trial_active', 'INTEGER DEFAULT 0'), ('last_image_reset', 'TEXT')]:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {dtype}")
        except: pass
    
    for k, v in [('free_input_chars','500'), ('free_output_words','50'), ('premium_input_chars','3000'), ('premium_output_words','300'), ('image_limit_free','3'), ('image_limit_premium','50')]:
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    conn.commit()

def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return cursor.fetchone()

def create_user(user_id, username):
    now = datetime.now().isoformat()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, joined, trial_start, trial_active, last_image_reset) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, username, now, now, 1, now))
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
    return user and user[3] and datetime.now().isoformat() < user[3]

def add_premium(user_id, days):
    cursor.execute("UPDATE users SET premium_until = ?, plan = 'premium' WHERE user_id = ?",
                ((datetime.now() + timedelta(days=days)).isoformat(), user_id))
    conn.commit()

def can_request(user_id):
    user = get_user(user_id)
    if not user: return True, 10
    if is_premium(user_id): return True, 999999
    used = user[4] or 0
    return used < 10, 10 - used

def add_request(user_id):
    cursor.execute("UPDATE users SET free_requests = free_requests + 1, total_requests = total_requests + 1 WHERE user_id = ?", (user_id,))
    conn.commit()

def get_setting(key):
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    r = cursor.fetchone()
    return r[0] if r else '0'

def set_setting(key, value):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()

def reset_image_count_if_needed(user_id):
    user = get_user(user_id)
    if not user: return
    if user[13]:
        try:
            if datetime.fromisoformat(user[13]).date() < datetime.now().date():
                cursor.execute("UPDATE users SET image_requests = 0, last_image_reset = ? WHERE user_id = ?", (datetime.now().isoformat(), user_id))
                conn.commit()
        except: pass

def get_image_limit(user_id):
    if is_premium(user_id):
        return int(get_setting('image_limit_premium') or 50)
    return int(get_setting('image_limit_free') or 3)

def can_generate_image(user_id):
    reset_image_count_if_needed(user_id)
    user = get_user(user_id)
    if not user: return True, 3
    used = user[8] or 0
    limit = get_image_limit(user_id)
    return used < limit, limit - used

def get_image_stats(user_id):
    reset_image_count_if_needed(user_id)
    user = get_user(user_id)
    if not user: return 0, 3, False
    used = user[8] or 0
    limit = get_image_limit(user_id)
    prem = is_premium(user_id)
    return used, limit, prem

def add_image_request(user_id):
    cursor.execute("UPDATE users SET image_requests = image_requests + 1 WHERE user_id = ?", (user_id,))
    conn.commit()

def get_stats():
    cursor.execute("SELECT COUNT(*) FROM users"); total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE premium_until > datetime('now')"); prem = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(total_requests) FROM users"); req = cursor.fetchone()[0] or 0
    return total, prem, req

def get_user_plan(user_id):
    user = get_user(user_id)
    return user[9] if user and len(user) > 9 else 'basic'

def set_user_plan(user_id, plan):
    cursor.execute("UPDATE users SET plan = ? WHERE user_id = ?", (plan, user_id))
    conn.commit()

def is_trial_active(user_id):
    user = get_user(user_id)
    if not user or len(user) < 12 or not user[11]: return False
    try:
        return (datetime.now() - datetime.fromisoformat(user[9])).days < 2
    except: return False

def get_trial_remaining(user_id):
    if not is_trial_active(user_id): return 0
    user = get_user(user_id)
    return max(0, 5 - (user[10] if user and len(user) > 10 else 0))

def use_trial_image(user_id):
    cursor.execute("UPDATE users SET trial_used = trial_used + 1 WHERE user_id = ?", (user_id,))
    conn.commit()

def get_mode(user_id):
    user = get_user(user_id)
    return user[7] if user and user[7] else "chat"
