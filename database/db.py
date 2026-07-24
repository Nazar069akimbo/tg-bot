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
            bonus_images INTEGER DEFAULT 0,
            bonus_requests INTEGER DEFAULT 0,
            last_checkin TEXT,
            checkin_streak INTEGER DEFAULT 0
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
        CREATE TABLE IF NOT EXISTS emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER,
            sender_name TEXT,
            receiver_id INTEGER,
            subject TEXT,
            text TEXT,
            date TEXT,
            is_read INTEGER DEFAULT 0
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
            'bonus_images': 'INTEGER DEFAULT 0',
            'bonus_requests': 'INTEGER DEFAULT 0',
            'last_checkin': 'TEXT',
            'checkin_streak': 'INTEGER DEFAULT 0'
        }
        for col, dtype in columns_to_add.items():
            if col not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {dtype}")
                    print(f"✅ Добавлена колонка {col}")
                except: pass
        default_settings = [
            ('free_input_chars', '500'),
            ('free_output_words', '50'),
            ('premium_input_chars', '3000'),
            ('premium_output_words', '300'),
            ('premium_deluxe_input_chars', '5000'),
            ('premium_deluxe_output_words', '500'),
            ('image_limit_free', '3'),
            ('image_limit_premium', '20'),
            ('image_limit_premium_deluxe', '50'),
            ('bonus_limit_free', '3'),
            ('bonus_limit_premium', '5'),
            ('bonus_limit_deluxe', '10')
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
            if user and user['plan'] == 'basic' and user['premium_until'] and user['premium_until'] > datetime.now().isoformat():
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
                (user_id, username, joined, trial_start, trial_active, last_image_reset, image_requests, free_requests, total_requests, referral_bonus_images, referral_bonus_requests, paid_premium, bonus_images, bonus_requests, last_checkin, checkin_streak) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, username, now, now, 1, now, 0, 0, 0, 0, 0, 0, 0, 0, None, 0))
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
            return True, f"✅ Вы получили +3 картинки и +10 запросов!"
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
            bonus_images = user['referral_bonus_images'] if user['referral_bonus_images'] else 0
            bonus_requests = user['referral_bonus_requests'] if user['referral_bonus_requests'] else 0
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
        premium_until = user['premium_until'] if user['premium_until'] else None
        return premium_until and datetime.now().isoformat() < premium_until
    except:
        return False

def get_user_plan(user_id):
    user = get_user(user_id)
    if user:
        plan = user['plan'] if user['plan'] else 'basic'
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
        print(f"🔍 add_premium: user_id={user_id}, days={days}, plan={plan}")
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            if not cursor.fetchone():
                print(f"❌ Пользователь {user_id} не найден!")
                return False
            new_date = (datetime.now() + timedelta(days=days)).isoformat()
            cursor.execute("""
                UPDATE users 
                SET premium_until = ?, plan = ? 
                WHERE user_id = ?
            """, (new_date, plan, user_id))
            if paid:
                cursor.execute("UPDATE users SET paid_premium = 1 WHERE user_id = ?", (user_id,))
            cursor.execute("SELECT plan, premium_until FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                print(f"📊 ПОСЛЕ: plan={row[0]}, premium_until={row[1]}")
            return True
    except Exception as e:
        print(f"❌ Ошибка add_premium: {e}")
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
            return True, 10, 0
        if is_premium(user_id):
            return True, 999999, 0
        used = user['free_requests'] if user['free_requests'] else 0
        bonus = user['bonus_requests'] if user['bonus_requests'] else 0
        total = 10 + bonus
        remaining = total - used
        if remaining > 0:
            return True, remaining, bonus
        return False, 0, bonus
    except:
        return True, 10, 0

def add_request(user_id):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            user = get_user(user_id)
            if is_premium(user_id):
                cursor.execute("UPDATE users SET total_requests = total_requests + 1 WHERE user_id = ?", (user_id,))
                return True
            bonus = user['bonus_requests'] if user['bonus_requests'] else 0
            if bonus > 0:
                cursor.execute("UPDATE users SET bonus_requests = bonus_requests - 1, total_requests = total_requests + 1 WHERE user_id = ?", (user_id,))
            else:
                cursor.execute("UPDATE users SET free_requests = free_requests + 1, total_requests = total_requests + 1 WHERE user_id = ?", (user_id,))
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
        'image_limit_premium': '20',
        'image_limit_premium_deluxe': '50',
        'bonus_limit_free': '3',
        'bonus_limit_premium': '5',
        'bonus_limit_deluxe': '10'
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
        if not user:
            return
        if is_premium(user_id):
            return
        last_reset = user['last_image_reset'] if user['last_image_reset'] else None
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
        return int(get_setting('image_limit_premium_deluxe') or 50)
    elif plan == 'premium':
        return int(get_setting('image_limit_premium') or 20)
    else:
        return int(get_setting('image_limit_free') or 3)

def can_generate_image(user_id):
    try:
        reset_image_count_if_needed(user_id)
        user = get_user(user_id)
        if not user:
            return True, 3, 0
        used = user['image_requests'] if user['image_requests'] else 0
        bonus = user['bonus_images'] if user['bonus_images'] else 0
        limit = get_image_limit(user_id) + bonus
        remaining = limit - used
        if remaining > 0:
            return True, remaining, bonus
        return False, 0, bonus
    except:
        return True, 3, 0

def get_image_stats(user_id):
    try:
        reset_image_count_if_needed(user_id)
        user = get_user(user_id)
        if not user:
            return 0, 3, False, 'basic', 0
        used = user['image_requests'] if user['image_requests'] else 0
        bonus = user['bonus_images'] if user['bonus_images'] else 0
        limit = get_image_limit(user_id) + bonus
        prem = is_premium(user_id)
        plan = get_user_plan(user_id)
        return used, limit, prem, plan, bonus
    except Exception as e:
        print(f"⚠️ Ошибка get_image_stats: {e}")
        return 0, 3, False, 'basic', 0

def add_image_request(user_id):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            user = get_user(user_id)
            bonus = user['bonus_images'] if user['bonus_images'] else 0
            if bonus > 0:
                cursor.execute("UPDATE users SET bonus_images = bonus_images - 1 WHERE user_id = ?", (user_id,))
            else:
                cursor.execute("UPDATE users SET image_requests = image_requests + 1 WHERE user_id = ?", (user_id,))
            return True
    except Exception as e:
        print(f"❌ Ошибка add_image_request: {e}")
        return False

def get_bonus_balance(user_id):
    try:
        user = get_user(user_id)
        if user:
            bonus_images = user['bonus_images'] if user['bonus_images'] else 0
            bonus_requests = user['bonus_requests'] if user['bonus_requests'] else 0
            return int(bonus_images) if bonus_images else 0, int(bonus_requests) if bonus_requests else 0
        return 0, 0
    except:
        return 0, 0

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
            return total, prem, req, images, paid
    except:
        return 0, 0, 0, 0, 0

def get_daily_stats(days=30):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            result = []
            for i in range(days):
                date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                cursor.execute("SELECT COUNT(*) FROM users WHERE date(joined) = ?", (date,))
                new_users = cursor.fetchone()[0] or 0
                cursor.execute("SELECT COUNT(*) FROM payments WHERE date(timestamp) = ? AND status = 'completed'", (date,))
                payments = cursor.fetchone()[0] or 0
                result.append({'date': date, 'new_users': new_users, 'payments': payments})
            return list(reversed(result))
    except:
        return []

def is_trial_active(user_id):
    try:
        user = get_user(user_id)
        if not user:
            return False
        trial_start = user['trial_start'] if user['trial_start'] else None
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
    if not user:
        return 0
    trial_used = user['trial_used'] if user['trial_used'] else 0
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
    return user['mode'] if user and user['mode'] else "chat"

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

def get_bonus_amount(user_id):
    plan = get_user_plan(user_id)
    if plan == 'premium_deluxe':
        return int(get_setting('bonus_limit_deluxe') or 10)
    elif plan == 'premium':
        return int(get_setting('bonus_limit_premium') or 5)
    else:
        return int(get_setting('bonus_limit_free') or 3)

def get_bonus_requests_amount(user_id):
    plan = get_user_plan(user_id)
    if plan == 'premium_deluxe':
        return 5
    elif plan == 'premium':
        return 3
    else:
        return 1

def do_daily_checkin(user_id):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            today = datetime.now().date().isoformat()
            cursor.execute("SELECT last_checkin, checkin_streak FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                cursor.execute("UPDATE users SET last_checkin = ?, checkin_streak = 1 WHERE user_id = ?", (today, user_id))
                return True, 1, "✅ Бонус дня! День 1 из 7."
            last_checkin = row[0]
            streak = row[1] if row[1] else 0
            if last_checkin == today:
                return False, streak, "✅ Ты уже получил бонус сегодня!"
            if last_checkin and datetime.fromisoformat(last_checkin).date() == datetime.now().date() - timedelta(days=1):
                streak += 1
            else:
                streak = 1
            bonus_images = get_bonus_amount(user_id)
            bonus_requests = get_bonus_requests_amount(user_id)
            if streak >= 7:
                bonus_images = bonus_images * 2
                bonus_requests = bonus_requests * 2
                cursor.execute("UPDATE users SET checkin_streak = 0, last_checkin = ? WHERE user_id = ?", (today, user_id))
                msg = f"🎉 7 ДНЕЙ! +{bonus_images} карт и +{bonus_requests} запросов!"
            else:
                cursor.execute("UPDATE users SET checkin_streak = ?, last_checkin = ? WHERE user_id = ?", (streak, today, user_id))
                msg = f"✅ День {streak} из 7! +{bonus_images} карт и +{bonus_requests} запросов."
            cursor.execute("UPDATE users SET bonus_images = bonus_images + ?, bonus_requests = bonus_requests + ? WHERE user_id = ?", 
                         (bonus_images, bonus_requests, user_id))
            return True, streak, msg
    except Exception as e:
        print(f"❌ Ошибка do_daily_checkin: {e}")
        return False, 0, "❌ Ошибка!"

def change_user_plan(user_id, new_plan):
    try:
        print(f"🔍 change_user_plan: user_id={user_id}, new_plan={new_plan}")
        user = get_user(user_id)
        if not user:
            print(f"❌ Пользователь {user_id} не найден!")
            return False, "Пользователь не найден!"
        print(f"📊 Текущий план: {user['plan']}, premium_until: {user['premium_until']}")
        if new_plan not in ['basic', 'premium', 'premium_deluxe']:
            print(f"❌ Неверный план: {new_plan}")
            return False, "Неверный план! Доступны: basic, premium, premium_deluxe"
        with get_db() as conn:
            cursor = conn.cursor()
            if new_plan == 'basic':
                cursor.execute("UPDATE users SET premium_until = NULL, plan = 'basic' WHERE user_id = ?", (user_id,))
                print(f"  ✅ Premium отключён для {user_id}")
            else:
                new_date = (datetime.now() + timedelta(days=30)).isoformat()
                cursor.execute("UPDATE users SET premium_until = ?, plan = ? WHERE user_id = ?", (new_date, new_plan, user_id))
                print(f"  ✅ {new_plan} выдан до {new_date} для {user_id}")
            cursor.execute("SELECT plan, premium_until FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                print(f"📊 ПОСЛЕ: plan={row[0]}, premium_until={row[1]}")
            plan_names = {"basic": "🔴 Бесплатный", "premium": "💎 Premium", "premium_deluxe": "👑 Premium Deluxe"}
            return True, f"✅ План изменён на {plan_names.get(new_plan, new_plan.upper())}!"
    except Exception as e:
        print(f"❌ Ошибка change_user_plan: {e}")
        import traceback
        traceback.print_exc()
        return False, f"❌ Ошибка: {e}"

# ===== НОВЫЕ ФУНКЦИИ ДЛЯ АДМИНКИ =====

def search_users(query):
    """Поиск пользователей по имени или ID"""
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, username, plan, is_blocked, total_requests, image_requests 
            FROM users 
            WHERE username LIKE ? OR user_id = ?
            ORDER BY total_requests DESC
            LIMIT 20
        """, (f"%{query}%", query if query.isdigit() else -1))
        return cursor.fetchall()

def get_user_card(user_id):
    """Полная карточка пользователя"""
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            return None
        
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
        referrals = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM payments WHERE user_id = ? AND status = 'completed'", (user_id,))
        payments_count = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT SUM(stars_amount) FROM payments WHERE user_id = ? AND status = 'completed'", (user_id,))
        total_spent = cursor.fetchone()[0] or 0
        
        return {
            'user': user,
            'referrals': referrals,
            'payments_count': payments_count,
            'total_spent': total_spent
        }

def get_top_users(limit=10):
    """Топ активных пользователей"""
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, username, total_requests, image_requests, plan 
            FROM users 
            ORDER BY total_requests DESC 
            LIMIT ?
        """, (limit,))
        return cursor.fetchall()

def create_promocode(code, bonus_images=0, bonus_requests=0, max_uses=1, expires_days=30):
    """Создание промокода"""
    from database.db import get_db
    from datetime import datetime, timedelta
    with get_db() as conn:
        cursor = conn.cursor()
        expires_at = (datetime.now() + timedelta(days=expires_days)).isoformat()
        cursor.execute("""
            INSERT INTO promocodes (code, bonus_images, bonus_requests, max_uses, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (code, bonus_images, bonus_requests, max_uses, datetime.now().isoformat(), expires_at))
        return True

def use_promocode(code, user_id):
    """Использование промокода"""
    from database.db import get_db
    from datetime import datetime
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, bonus_images, bonus_requests, max_uses, used FROM promocodes WHERE code = ? AND expires_at > datetime('now')", (code,))
        promo = cursor.fetchone()
        if not promo:
            return False, "Промокод не найден или истёк"
        if promo['used'] >= promo['max_uses']:
            return False, "Промокод уже использован"
        cursor.execute("SELECT id FROM promocode_uses WHERE promocode_id = ? AND user_id = ?", (promo['id'], user_id))
        if cursor.fetchone():
            return False, "Вы уже использовали этот промокод"
        cursor.execute("INSERT INTO promocode_uses (promocode_id, user_id, used_at) VALUES (?, ?, ?)", 
                      (promo['id'], user_id, datetime.now().isoformat()))
        cursor.execute("UPDATE promocodes SET used = used + 1 WHERE id = ?", (promo['id'],))
        if promo['bonus_images'] > 0:
            cursor.execute("UPDATE users SET bonus_images = bonus_images + ? WHERE user_id = ?", (promo['bonus_images'], user_id))
        if promo['bonus_requests'] > 0:
            cursor.execute("UPDATE users SET bonus_requests = bonus_requests + ? WHERE user_id = ?", (promo['bonus_requests'], user_id))
        return True, f"✅ Промокод активирован! +{promo['bonus_images']} карт, +{promo['bonus_requests']} запросов"

def get_promocodes():
    """Список всех промокодов"""
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM promocodes ORDER BY created_at DESC")
        return cursor.fetchall()

def export_users_csv():
    """Экспорт пользователей в CSV"""
    from database.db import get_db
    import csv
    from io import StringIO
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, joined, plan, premium_until, total_requests, image_requests, is_blocked FROM users")
        users = cursor.fetchall()
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'Имя', 'Дата регистрации', 'План', 'Premium до', 'Запросы', 'Картинки', 'Заблокирован'])
        for u in users:
            writer.writerow([u['user_id'], u['username'], u['joined'], u['plan'], u['premium_until'], u['total_requests'], u['image_requests'], u['is_blocked']])
        return output.getvalue()

def get_backup_list():
    """Список бэкапов из GitHub"""
    import requests
    import os
    token = os.getenv('GITHUB_TOKEN')
    repo = os.getenv('GITHUB_BACKUP_REPO')
    if not token or not repo:
        return []
    headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
    url = f'https://api.github.com/repos/{repo}/contents/backups'
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return []
    files = [f for f in resp.json() if f['name'].endswith('.db')]
    files.sort(key=lambda x: x['name'], reverse=True)
    return files

def restore_backup(filename):
    """Восстановление бэкапа по имени файла"""
    import requests
    import os
    import shutil
    token = os.getenv('GITHUB_TOKEN')
    repo = os.getenv('GITHUB_BACKUP_REPO')
    if not token or not repo:
        return False
    headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
    url = f'https://api.github.com/repos/{repo}/contents/backups/{filename}'
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return False
    file_url = resp.json()['download_url']
    resp = requests.get(file_url)
    if resp.status_code != 200:
        return False
    os.makedirs('data', exist_ok=True)
    with open('data/repsolver.db', 'wb') as f:
        f.write(resp.content)
    return True

def log_admin_action(admin_id, action, target_id=None, details=None):
    """Логирование действий админа"""
    from database.db import get_db
    from datetime import datetime
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO admin_log (admin_id, action, target_id, details, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (admin_id, action, target_id, details, datetime.now().isoformat()))
