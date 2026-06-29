import sqlite3, os
from datetime import datetime, timedelta

DB_PATH = 'data/repsolver.db'
os.makedirs('data', exist_ok=True)
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

def init_db():
    # СОЗДАЁМ ВСЕ ТАБЛИЦЫ
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
    
    # Проверяем колонки
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
            return True
        
        cursor.execute("""
            INSERT INTO users 
            (user_id, username, joined, trial_start, trial_active, last_image_reset, image_requests, free_requests, total_requests) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, username, now, now, 1, now, 0, 0, 0))
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
        if not user:
            return False
        premium_until = user[3] if len(user) > 3 else None
        return premium_until and datetime.now().isoformat() < premium_until
    except:
        return False

def add_premium(user_id, days):
    try:
        cursor.execute("UPDATE users SET premium_until = ?, plan = 'premium' WHERE user_id = ?",
                    ((datetime.now() + timedelta(days=days)).isoformat(), user_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"⚠️ Ошибка add_premium: {e}")
        return False

def can_request(user_id):
    try:
        user = get_user(user_id)
        if not user: return True, 10
        if is_premium(user_id): return True, 999999
        used = user[4] if len(user) > 4 and user[4] else 0
        try:
            used = int(used)
        except:
            used = 0
        return used < 10, 10 - used
    except:
        return True, 10

def add_request(user_id):
    try:
        cursor.execute("UPDATE users SET free_requests = free_requests + 1, total_requests = total_requests + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        print(f"✅ Добавлен текстовый запрос для {user_id}")
        return True
    except Exception as e:
        print(f"❌ Ошибка add_request: {e}")
        return False

def get_setting(key):
    try:
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
        'image_limit_free': '3',
        'image_limit_premium': '50'
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
        if not user:
            return
        if len(user) < 14:
            return
        last_reset = user[13] if len(user) > 13 else None
        if not last_reset:
            try:
                cursor.execute("UPDATE users SET last_image_reset = ? WHERE user_id = ?", (datetime.now().isoformat(), user_id))
                conn.commit()
                print(f"🔄 Установлен last_image_reset для {user_id}")
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
                    print(f"🔄 Сброшен счётчик картинок для {user_id}")
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
        used = 0
        if len(user) > 8 and user[8]:
            try:
                used = int(user[8])
            except:
                used = 0
        limit = get_image_limit(user_id)
        print(f"📊 can_generate_image: user={user_id}, used={used}, limit={limit}")
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
        print(f"📊 get_image_stats: user={user_id}, used={used}, limit={limit}, prem={prem}")
        return used, limit, prem
    except Exception as e:
        print(f"⚠️ Ошибка get_image_stats: {e}")
        return 0, 3, False

def add_image_request(user_id):
    try:
        print(f"📸 add_image_request: НАЧАЛО для {user_id}")
        
        # Проверяем существование колонки
        cursor.execute("PRAGMA table_info(users)")
        cols = [row[1] for row in cursor.fetchall()]
        if 'image_requests' not in cols:
            print(f"❌ Колонка image_requests не существует! Создаём...")
            cursor.execute("ALTER TABLE users ADD COLUMN image_requests INTEGER DEFAULT 0")
            conn.commit()
        
        # Увеличиваем счётчик
        cursor.execute("UPDATE users SET image_requests = image_requests + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        print(f"✅ add_image_request: Успешно обновлён image_requests для {user_id}")
        
        # Проверяем результат
        cursor.execute("SELECT image_requests FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        if result:
            print(f"📊 add_image_request: Новое значение = {result[0]}")
        return True
    except Exception as e:
        print(f"❌ Ошибка add_image_request: {e}")
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

def get_user_plan(user_id):
    user = get_user(user_id)
    return user[9] if user and len(user) > 9 and user[9] else 'basic'

def set_user_plan(user_id, plan):
    try:
        cursor.execute("UPDATE users SET plan = ? WHERE user_id = ?", (plan, user_id))
        conn.commit()
        return True
    except:
        return False

def is_trial_active(user_id):
    try:
        user = get_user(user_id)
        if not user or len(user) < 12 or not user[11]:
            return False
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
    try:
        cursor.execute("UPDATE users SET trial_used = trial_used + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        print(f"✅ Использована пробная картинка для {user_id}")
        return True
    except Exception as e:
        print(f"❌ Ошибка use_trial_image: {e}")
        return False

def get_mode(user_id):
    user = get_user(user_id)
    return user[7] if user and len(user) > 7 and user[7] else "chat"
