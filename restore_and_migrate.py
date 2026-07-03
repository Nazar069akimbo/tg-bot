import sqlite3
import os
import shutil
from datetime import datetime

# ПУТИ
BACKUP_PATH = "repsolver_backup_2026-06-30_21-54-51.db"
DB_PATH = "data/repsolver.db"

def restore_and_migrate():
    # 1. Удаляем старую БД если есть
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print("🗑️ Старая БД удалена")
    
    # 2. Копируем бекап
    os.makedirs("data", exist_ok=True)
    shutil.copy2(BACKUP_PATH, DB_PATH)
    print("✅ Бекап скопирован")
    
    # 3. Открываем БД и добавляем колонки
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Проверяем существующие колонки
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
    
    # 4. Проверяем другие таблицы
    tables = {
        'referrals': 'id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER, referred_id INTEGER, joined TEXT, bonus_given INTEGER DEFAULT 0',
        'admins': 'user_id INTEGER PRIMARY KEY, added_at TEXT',
        'payments': 'id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, stars_amount INTEGER, telegram_payload TEXT, status TEXT, timestamp TEXT, plan TEXT',
        'messages_to_admin': 'id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, text TEXT, date TEXT, status TEXT DEFAULT "new"',
        'settings': 'key TEXT PRIMARY KEY, value TEXT'
    }
    
    for table, schema in tables.items():
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
        if not cursor.fetchone():
            cursor.execute(f"CREATE TABLE {table} ({schema})")
            print(f"✅ Таблица {table} создана")
    
    # 5. Настройки по умолчанию
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
    
    # 6. Добавляем админа
    cursor.execute("INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)", 
                   (6957852385, datetime.now().isoformat()))
    
    # 7. 🔥 СИНХРОНИЗАЦИЯ: если есть premium_until, но plan basic → исправляем
    cursor.execute("UPDATE users SET plan = 'premium' WHERE premium_until IS NOT NULL AND premium_until > datetime('now') AND (plan IS NULL OR plan = 'basic')")
    print("✅ Синхронизация планов выполнена")
    
    conn.commit()
    conn.close()
    
    print("✅ Восстановление и миграция завершены!")
    
    # Проверяем
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    print(f"📊 Всего пользователей в БД: {count}")
    cursor.execute("SELECT user_id, plan, premium_until FROM users LIMIT 5")
    print("📋 Пример пользователей:")
    for row in cursor.fetchall():
        print(f"   ID: {row[0]}, план: {row[1]}, premium_until: {row[2]}")
    conn.close()

if __name__ == "__main__":
    restore_and_migrate()
