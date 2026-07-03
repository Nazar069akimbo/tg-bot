import sqlite3, os
from datetime import datetime, timedelta
from contextlib import contextmanager

DB_PATH = 'data/repsolver.db'
os.makedirs('data', exist_ok=True)

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        
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
            last_image_reset TEXT,
            referral_bonus_images INTEGER DEFAULT 0,
            referral_bonus_requests INTEGER DEFAULT 0,
            paid_premium INTEGER DEFAULT 0,
            caps_used INTEGER DEFAULT 0
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
        
        cursor.execute("PRAGMA table_info(users)")
        existing_cols = [row[1] for row in cursor.fetchall()]
        
        columns_to_add = {
            'image_requests': 'INTEGER DEFAULT 0',
            'plan': 'TEXT DEFAULT "basic"',
            'trial_start': 'TEXT',
            'trial_used': 'INTEGER DEFAULT 0',
            'trial_active': 'INTEGER DEFAULT 0',
            'last_image_reset': 'TEXT',
            'referral_bonus_images': 'INTEGER DEFAULT 0',
            'referral_bonus_requests': 'INTEGER DEFAULT 0',
            'paid_premium': 'INTEGER DEFAULT 0',
            'caps_used': 'INTEGER DEFAULT 0'
        }
        
        for col, dtype in columns_to_add.items():
            if col not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {dtype}")
                    print(f"✅ Добавлена колонка {col}")
                except:
                    pass
        
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
        
        cursor.execute("INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)", 
                       (6957852385, datetime.now().isoformat()))
        
        cursor.execute("UPDATE users SET plan = 'premium' WHERE premium_until IS NOT NULL AND premium_until > datetime('now') AND plan = 'basic'")
        print("✅ База данных готова")

def get_user(user_id):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = cursor.fetchone()
            if user and len(user) > 9 and user[9] == 'basic' and user[3] and user[3] > datetime.now().isoformat():
                cursor.execute("UPDATE users SET plan = 'premium' WHERE user_id = ?", (user_id,))
                cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
                user = cursor.fetchone()
            return user
    except Exception as e:
        print(f"⚠️ Ошибка get_user: {e}")
        return None

def create_user(user_id, username):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            if cursor.fetchone():
                return True
            cursor.execute("""
                INSERT INTO users 
                (user_id, username, joined, trial_start, trial_active, last_image_reset, image_requests, free_requests, total_requests, referral_bonus_images, referral_bonus_requests, paid_premium, caps_used) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, username, now, now, 1, now, 0, 0, 0, 0, 0, 0, 0))
            print(f"✅ Создан пользователь {user_id}")
            return True
    except Exception as e:
        print(f"❌ Ошибка create_user: {e}")
        return False

def add_referral(referrer_id, referred_id):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            if referrer_id == referred_id:
                return False, "Нельзя пригласить самого себя!"
            
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (referrer_id,))
            if not cursor.fetchone():
                return False, "Реферер не найден!"
            
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (referred_id,))
            if not cursor.fetchone():
                return False, "Пользователь не найден!"
            
            cursor.execute("SELECT referrer_id FROM referrals WHERE referred_id = ?", (referred_id,))
            if cursor.fetchone():
                return False, "Этот пользователь уже был приглашён!"
            
            cursor.execute("SELECT id FROM referrals WHERE referrer_id = ? AND referred_id = ?", (referrer_id, referred_id))
            if cursor.fetchone():
                return False, "Вы уже приглашали этого пользователя!"
            
            cursor.execute("INSERT INTO referrals (referrer_id, referred_id, joined) VALUES (?, ?, ?)",
                        (referrer_id, referred_id, datetime.now().isoformat()))
            
            cursor.execute("UPDATE users SET referral_bonus_images = referral_bonus_images + 3 WHERE user_id = ?", (referrer_id,))
            cursor.execute("UPDATE users SET referral_bonus_requests = referral_bonus_requests + 10 WHERE user_id = ?", (referrer_id,))
            
            return True, f"✅ Вы получили +3 картинки и +10 запросов за приглашение!"
    except Exception as e:
        print(f"⚠️ Ошибка add_referral: {e}")
        return False, f"Ошибка: {e}"

def get_referral_count(user_id):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
            return cursor.fetchone()[0] or 0
    except:
        return 0

def get_referral_bonuses(user_id):
    try:
        user = get_user(user_id)
        if user:
            bonus_images = user[14] if len(user) > 14 and user[14] else 0
            bonus_requests = user[15] if len(user) > 15 and user[15] else 0
            return bonus_images, bonus_requests
        return 0, 0
    except:
        return 0, 0

def mark_paid_premium(user_id):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET paid_premium = 1 WHERE user_id = ?", (user_id,))
            return True
    except:
        return False

def get_paid_premium_count():
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users WHERE paid_premium = 1")
            return cursor.fetchone()[0] or 0
    except:
        return 0

def is_admin(user_id):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
            return cursor.fetchone() is not None
    except:
        return False

def add_admin(user_id):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)", (user_id, datetime.now().isoformat()))
            return True
    except:
        return False

def is_premium(user_id):
    try:
        user = get_user(user_id)
        if not user:
            return False
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
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET plan = ? WHERE user_id = ?", (plan, user_id))
            return True
    except:
        return False

def add_premium(user_id, days, plan='premium', paid=False):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            new_date = (datetime.now() + timedelta(days=days)).isoformat()
            cursor.execute("UPDATE users SET premium_until = ?, plan = ? WHERE user_id = ?",
                        (new_date, plan, user_id))
            if paid:
                cursor.execute("UPDATE users SET paid_premium = 1 WHERE user_id = ?", (user_id,))
            return True
    except:
        return False

def remove_premium(user_id):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET premium_until = NULL, plan = 'basic' WHERE user_id = ?", (user_id,))
            return True
    except:
        return False

def block_user(user_id):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_blocked = 1 WHERE user_id = ?", (user_id,))
            return True
    except:
        return False

def unblock_user(user_id):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_blocked = 0 WHERE user_id = ?", (user_id,))
            return True
    except:
        return False

def can_request(user_id):
    try:
        user = get_user(user_id)
        if not user:
            return True, 10
        if is_premium(user_id):
            return True, 999999
        used = user[4] if len(user) > 4 and user[4] else 0
        used = int(used) if used else 0
        bonus = user[15] if len(user) > 15 and user[15] else 0
        total = 10 + bonus
        return used < total, total - used
    except:
        return True, 10

def add_request(user_id):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET free_requests = free_requests + 1, total_requests = total_requests + 1 WHERE user_id = ?", (user_id,))
            cursor.execute("UPDATE users SET caps_used = caps_used + 100 WHERE user_id = ?", (user_id,))
            return True
    except:
        return False

def get_setting(key):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            r = cursor.fetchone()
            if r:
                return r[0]
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
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
            return True
    except:
        return False

def reset_image_count_if_needed(user_id):
    try:
        user = get_user(user_id)
        if not user or len(user) < 14:
            return
        last_reset = user[13] if len(user) > 13 else None
        if not last_reset:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET last_image_reset = ? WHERE user_id = ?", (datetime.now().isoformat(), user_id))
            return
        if last_reset:
            last_date = datetime.fromisoformat(last_reset)
            today = datetime.now()
            if last_date.date() < today.date():
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE users SET image_requests = 0, last_image_reset = ? WHERE user_id = ?", 
                                  (today.isoformat(), user_id))
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
        if not user:
            return True, 3
        used = user[8] if len(user) > 8 and user[8] else 0
        used = int(used) if used else 0
        bonus = user[14] if len(user) > 14 and user[14] else 0
        limit = get_image_limit(user_id) + bonus
        return used < limit, limit - used
    except:
        return True, 3

def get_image_stats(user_id):
    try:
        reset_image_count_if_needed(user_id)
        user = get_user(user_id)
        if not user:
            return 0, 3, False, 'basic'
        used = user[8] if len(user) > 8 and user[8] else 0
        used = int(used) if used else 0
        bonus = user[14] if len(user) > 14 and user[14] else 0
        limit = get_image_limit(user_id) + bonus
        prem = is_premium(user_id)
        plan = get_user_plan(user_id)
        return used, limit, prem, plan
    except Exception as e:
        print(f"⚠️ Ошибка get_image_stats: {e}")
        return 0, 3, False, 'basic'

def add_image_request(user_id):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET image_requests = image_requests + 1 WHERE user_id = ?", (user_id,))
            cursor.execute("UPDATE users SET caps_used = caps_used + 1700 WHERE user_id = ?", (user_id,))
            return True
    except Exception as e:
        print(f"❌ Ошибка add_image_request: {e}")
        return False

def get_stats():
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM users WHERE premium_until > datetime('now')")
            prem = cursor.fetchone()[0]
            cursor.execute("SELECT SUM(total_requests) FROM users")
            req = cursor.fetchone()[0] or 0
            cursor.execute("SELECT SUM(image_requests) FROM users")
            images = cursor.fetchone()[0] or 0
            cursor.execute("SELECT COUNT(*) FROM users WHERE paid_premium = 1")
            paid = cursor.fetchone()[0] or 0
            cursor.execute("SELECT SUM(caps_used) FROM users")
            caps = cursor.fetchone()[0] or 0
            return total, prem, req, images, paid, caps
    except:
        return 0, 0, 0, 0, 0, 0

def get_daily_stats(days=30):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            result = []
            for i in range(days):
                date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                cursor.execute("""
                    SELECT COUNT(*) FROM users WHERE date(joined) = ?
                """, (date,))
                new_users = cursor.fetchone()[0] or 0
                cursor.execute("""
                    SELECT COUNT(*) FROM payments WHERE date(timestamp) = ? AND status = 'completed'
                """, (date,))
                payments = cursor.fetchone()[0] or 0
                result.append({'date': date, 'new_users': new_users, 'payments': payments})
            return list(reversed(result))
    except:
        return []

def is_trial_active(user_id):
    try:
        user = get_user(user_id)
        if not user or len(user) < 11:
            return False
        trial_start = user[10] if len(user) > 10 else None
        if not trial_start:
            return False
        start_date = datetime.fromisoformat(trial_start)
        return (datetime.now() - start_date).days < 2
    except:
        return False

def get_trial_remaining(user_id):
    if not is_trial_active(user_id):
        return 0
    user = get_user(user_id)
    if not user or len(user) < 12:
        return 0
    trial_used = user[11] if user[11] else 0
    trial_used = int(trial_used) if trial_used else 0
    return max(0, 5 - trial_used)

def use_trial_image(user_id):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET trial_used = trial_used + 1 WHERE user_id = ?", (user_id,))
            return True
    except:
        return False

def get_mode(user_id):
    user = get_user(user_id)
    return user[7] if user and len(user) > 7 and user[7] else "chat"

def get_messages_count():
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM messages_to_admin WHERE status = 'new'")
            return cursor.fetchone()[0] or 0
    except:
        return 0

def delete_message(message_id):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM messages_to_admin WHERE id = ?", (message_id,))
            return True
    except:
        return False

def get_message_by_id(message_id):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM messages_to_admin WHERE id = ?", (message_id,))
            return cursor.fetchone()
    except:
        return None
