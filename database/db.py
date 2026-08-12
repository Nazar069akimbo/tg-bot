import sqlite3
import os
import json
import secrets
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
    """Инициализация БД со всеми таблицами"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # ===== ОСНОВНЫЕ ТАБЛИЦЫ =====
        
        # Пользователи (расширенные)
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
        
        # ===== НОВАЯ ТАБЛИЦА: ПАМЯТЬ ПОЛЬЗОВАТЕЛЯ =====
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_memory (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            favorite_style TEXT,
            favorite_colors TEXT,      -- JSON массив
            preferred_model TEXT,
            last_prompt TEXT,
            context_history TEXT,      -- JSON массив последних 20 запросов
            preferences TEXT,          -- JSON с любыми предпочтениями
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        ''')
        
        # ===== НОВАЯ ТАБЛИЦА: ИСТОРИЯ КАРТИНОК (ДЛЯ ЦЕПОЧЕК ПРАВОК) =====
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS images_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            prompt TEXT,
            enhanced_prompt TEXT,
            model TEXT,
            image_data TEXT,           -- base64 или ссылка
            previous_id INTEGER,       -- ссылка на предыдущую картинку (для цепочки)
            session_id TEXT,           -- уникальный ID сессии правок
            edit_type TEXT,            -- 'original', 'color', 'add', 'remove', 'background', 'style'
            edit_text TEXT,            -- что написал пользователь
            version INTEGER DEFAULT 1,
            created_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (previous_id) REFERENCES images_history(id)
        )
        ''')
        
        # ===== НОВАЯ ТАБЛИЦА: СЕССИИ ПРАВОК =====
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS edit_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            session_id TEXT UNIQUE,
            original_image_id INTEGER,
            current_image_id INTEGER,
            is_active INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        ''')
        
        # ===== ОСТАЛЬНЫЕ ТАБЛИЦЫ =====
        
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
            used_at TEXT,
            FOREIGN KEY (promocode_id) REFERENCES promocodes(id)
        )
        ''')
        
        # ===== МИГРАЦИИ ДЛЯ СУЩЕСТВУЮЩИХ ТАБЛИЦ =====
        
        # Добавляем новые колонки в users если их нет
        cursor.execute("PRAGMA table_info(users)")
        existing_cols = [row[1] for row in cursor.fetchall()]
        
        new_cols = {
            'tokens': 'INTEGER DEFAULT 0',
            'trial_start': 'TEXT',
            'trial_active': 'INTEGER DEFAULT 0',
            'text_requests': 'INTEGER DEFAULT 0',
            'max_text_requests': 'INTEGER DEFAULT 10',
            'text_requests_reset': 'TEXT',
            'plan': 'TEXT DEFAULT "basic"',
            'premium_until': 'TEXT',
            'total_requests': 'INTEGER DEFAULT 0',
            'image_requests': 'INTEGER DEFAULT 0',
            'last_image_reset': 'TEXT',
            'referral_bonus_images': 'INTEGER DEFAULT 0',
            'referral_bonus_requests': 'INTEGER DEFAULT 0',
            'paid_premium': 'INTEGER DEFAULT 0',
            'bonus_images': 'INTEGER DEFAULT 0',
            'bonus_requests': 'INTEGER DEFAULT 0',
            'last_checkin': 'TEXT',
            'checkin_streak': 'INTEGER DEFAULT 0',
            'total_spent': 'INTEGER DEFAULT 0'
        }
        
        for col, dtype in new_cols.items():
            if col not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {dtype}")
                    print(f"✅ Добавлена колонка {col}")
                except:
                    pass
        
        # Добавляем колонку plan в payments
        cursor.execute("PRAGMA table_info(payments)")
        payment_cols = [row[1] for row in cursor.fetchall()]
        if 'plan' not in payment_cols:
            try:
                cursor.execute("ALTER TABLE payments ADD COLUMN plan TEXT")
                print("✅ Добавлена колонка plan в payments")
            except:
                pass
        
        # ===== НАСТРОЙКИ ПО УМОЛЧАНИЮ =====
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
        
        # Добавляем админа
        cursor.execute("INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)", 
                       (6957852385, datetime.now().isoformat()))
        
        print("✅ База данных готова")


# ==================== ОСНОВНЫЕ ФУНКЦИИ ====================

def get_user(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return cursor.fetchone()

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
        return True

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


# ==================== ТОКЕНЫ ====================

def get_tokens(user_id):
    user = get_user(user_id)
    if not user:
        return 0
    return user['tokens'] if user['tokens'] else 0

def add_tokens(user_id, amount):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET tokens = tokens + ? WHERE user_id = ?", (amount, user_id))

def spend_tokens(user_id, amount):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT tokens FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row and row[0] >= amount:
            cursor.execute("UPDATE users SET tokens = tokens - ? WHERE user_id = ?", (amount, user_id))
            return True
        return False


# ==================== ПАМЯТЬ ПОЛЬЗОВАТЕЛЯ (НОВОЕ!) ====================

def get_user_memory(user_id):
    """Получить память пользователя"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_memory WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)

def init_user_memory(user_id):
    """Создать запись памяти для пользователя"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO user_memory (user_id, created_at, updated_at, context_history)
            VALUES (?, ?, ?, ?)
        """, (user_id, datetime.now().isoformat(), datetime.now().isoformat(), json.dumps([])))
        return True

def update_user_memory(user_id, data):
    """Обновить память пользователя"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Проверяем существование
        cursor.execute("SELECT user_id FROM user_memory WHERE user_id = ?", (user_id,))
        if not cursor.fetchone():
            init_user_memory(user_id)
        
        # Строим SET часть
        set_parts = []
        values = []
        for key, value in data.items():
            if key in ['name', 'favorite_style', 'favorite_colors', 'preferred_model', 'last_prompt', 'context_history', 'preferences']:
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
    """Добавить запрос в историю контекста"""
    memory = get_user_memory(user_id)
    if not memory:
        init_user_memory(user_id)
        memory = get_user_memory(user_id)
    
    history = json.loads(memory.get('context_history', '[]'))
    
    entry = {
        'prompt': prompt,
        'image_id': image_id,
        'edit_type': edit_type,
        'timestamp': datetime.now().isoformat()
    }
    history.append(entry)
    
    # Храним последние 20 запросов
    if len(history) > 20:
        history = history[-20:]
    
    update_user_memory(user_id, {'context_history': json.dumps(history)})
    return entry

def get_context_history(user_id, limit=10):
    """Получить историю контекста"""
    memory = get_user_memory(user_id)
    if not memory:
        return []
    history = json.loads(memory.get('context_history', '[]'))
    return history[-limit:] if history else []

def set_user_name(user_id, name):
    """Запомнить имя пользователя"""
    update_user_memory(user_id, {'name': name})

def set_user_style(user_id, style):
    """Запомнить любимый стиль пользователя"""
    update_user_memory(user_id, {'favorite_style': style})

def get_user_preferences(user_id):
    """Получить все предпочтения пользователя"""
    memory = get_user_memory(user_id)
    if not memory:
        return {}
    prefs = memory.get('preferences')
    if prefs:
        if isinstance(prefs, str):
            try:
                return json.loads(prefs)
            except:
                return {}
        return prefs
    return {}


# ==================== ИСТОРИЯ КАРТИНОК (ДЛЯ ПРАВОК) ====================

def save_image_to_history(user_id, prompt, enhanced_prompt, model, image_data, 
                          previous_id=None, session_id=None, edit_type=None, edit_text=None):
    """Сохранить картинку в историю для цепочки правок"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        if not session_id:
            session_id = secrets.token_hex(8)
        
        # Получаем версию
        cursor.execute("""
            SELECT COUNT(*) + 1 FROM images_history 
            WHERE user_id = ? AND session_id = ?
        """, (user_id, session_id))
        version = cursor.fetchone()[0] or 1
        
        cursor.execute("""
            INSERT INTO images_history 
            (user_id, prompt, enhanced_prompt, model, image_data, previous_id, session_id, 
             edit_type, edit_text, version, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, prompt, enhanced_prompt, model, image_data, previous_id, session_id,
              edit_type, edit_text, version, datetime.now().isoformat()))
        
        image_id = cursor.lastrowid
        
        # Обновляем сессию
        cursor.execute("""
            INSERT INTO edit_sessions (user_id, session_id, original_image_id, current_image_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET 
                current_image_id = ?, updated_at = ?
        """, (user_id, session_id, previous_id or image_id, image_id, 
              datetime.now().isoformat(), datetime.now().isoformat(),
              image_id, datetime.now().isoformat()))
        
        # Добавляем в контекст
        add_to_context(user_id, prompt, image_id, edit_type)
        
        return image_id, session_id

def get_last_image(user_id, session_id=None):
    """Получить последнюю картинку пользователя или сессии"""
    with get_db() as conn:
        cursor = conn.cursor()
        if session_id:
            cursor.execute("""
                SELECT * FROM images_history 
                WHERE user_id = ? AND session_id = ? 
                ORDER BY id DESC LIMIT 1
            """, (user_id, session_id))
        else:
            cursor.execute("""
                SELECT * FROM images_history 
                WHERE user_id = ? 
                ORDER BY id DESC LIMIT 1
            """, (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_image_by_id(image_id):
    """Получить картинку по ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM images_history WHERE id = ?", (image_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_image_chain(user_id, image_id):
    """Получить ВСЮ цепочку правок для картинки"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            WITH RECURSIVE chain AS (
                SELECT * FROM images_history WHERE id = ?
                UNION ALL
                SELECT h.* FROM images_history h
                JOIN chain c ON h.id = c.previous_id
            )
            SELECT * FROM chain ORDER BY id ASC
        """, (image_id,))
        return [dict(row) for row in cursor.fetchall()]

def get_image_chain_by_session(user_id, session_id):
    """Получить всю цепочку по сессии"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM images_history 
            WHERE user_id = ? AND session_id = ? 
            ORDER BY id ASC
        """, (user_id, session_id))
        return [dict(row) for row in cursor.fetchall()]

def get_edit_session(user_id, session_id):
    """Получить информацию о сессии правок"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM edit_sessions 
            WHERE user_id = ? AND session_id = ?
        """, (user_id, session_id))
        return dict(cursor.fetchone()) if cursor.fetchone() else None

def close_edit_session(session_id):
    """Закрыть сессию правок"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE edit_sessions SET is_active = 0, updated_at = ?
            WHERE session_id = ?
        """, (datetime.now().isoformat(), session_id))

def get_full_context_prompt(user_id, session_id):
    """Собрать полный промпт из всей цепочки правок"""
    chain = get_image_chain_by_session(user_id, session_id)
    if not chain:
        return None
    
    # Собираем все промпты в один
    prompts = []
    for img in chain:
        if img['edit_text']:
            prompts.append(img['edit_text'])
        else:
            prompts.append(img['prompt'])
    
    return " + ".join(prompts)

def get_edit_version(user_id, session_id):
    """Получить номер текущей версии правки"""
    chain = get_image_chain_by_session(user_id, session_id)
    return len(chain)


# ==================== ТЕКСТОВЫЕ ЗАПРОСЫ ====================

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


# ==================== ТРИАЛ ====================

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


# ==================== РЕФЕРАЛЫ ====================

def add_referral(referrer_id, referred_id):
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
        add_tokens(referrer_id, 20)
        return True, f"✅ Реферал засчитан! +20 токенов"

def get_referral_count(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
        return cursor.fetchone()[0] or 0


# ==================== СТАТИСТИКА ====================

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


# ==================== БЛОКИРОВКА ====================

def block_user(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_blocked = 1 WHERE user_id = ?", (user_id,))
        return True

def unblock_user(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_blocked = 0 WHERE user_id = ?", (user_id,))
        return True


# ==================== ПРОМОКОДЫ ====================

def use_promocode(code, user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, bonus_tokens, max_uses, used 
            FROM promocodes 
            WHERE code = ? AND expires_at > datetime('now')
        """, (code,))
        promo = cursor.fetchone()
        if not promo:
            return False, "❌ Промокод не найден или истёк"
        if promo['used'] >= promo['max_uses']:
            return False, "❌ Промокод уже использован"
        cursor.execute("SELECT id FROM promocode_uses WHERE promocode_id = ? AND user_id = ?", (promo['id'], user_id))
        if cursor.fetchone():
            return False, "❌ Вы уже использовали этот промокод"
        cursor.execute("INSERT INTO promocode_uses (promocode_id, user_id, used_at) VALUES (?, ?, ?)", 
                      (promo['id'], user_id, datetime.now().isoformat()))
        cursor.execute("UPDATE promocodes SET used = used + 1 WHERE id = ?", (promo['id'],))
        if promo['bonus_tokens'] > 0:
            cursor.execute("UPDATE users SET tokens = tokens + ? WHERE user_id = ?", (promo['bonus_tokens'], user_id))
        return True, f"✅ Промокод активирован! +{promo['bonus_tokens']} токенов!"


# ==================== ПЛАТЕЖИ ====================

def create_payment(user_id, stars_amount, payload, plan="tokens"):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO payments (user_id, stars_amount, telegram_payload, status, timestamp, plan)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, stars_amount, payload, "pending", datetime.now().isoformat(), plan))
        return True

def complete_payment(payload):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE payments SET status = 'completed' WHERE telegram_payload = ?", (payload,))
        cursor.execute("SELECT user_id, stars_amount, plan FROM payments WHERE telegram_payload = ?", (payload,))
        return cursor.fetchone()


# ==================== НАСТРОЙКИ ====================

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
        return True


# ==================== ВСПОМОГАТЕЛЬНЫЕ ====================

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

def do_backup():
    try:
        from backup import GitHubBackup
        GitHubBackup().backup_db()
    except:
        pass

def get_referral_count(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
        return cursor.fetchone()[0] or 0

def get_user_count():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        return cursor.fetchone()[0] or 0
