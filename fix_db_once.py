from database.db import get_db
import sqlite3

print("🔧 Применяю миграцию БД...")

DB_PATH = 'data/repsolver.db'

# Проверяем, есть ли колонка tokens
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(users)")
cols = [row[1] for row in cursor.fetchall()]
conn.close()

if 'tokens' not in cols:
    print("✅ Добавляю колонку tokens...")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("ALTER TABLE users ADD COLUMN tokens INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE users ADD COLUMN trial_start TEXT")
        cursor.execute("ALTER TABLE users ADD COLUMN text_requests INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE users ADD COLUMN max_text_requests INTEGER DEFAULT 10")
        cursor.execute("ALTER TABLE users ADD COLUMN text_requests_reset TEXT")
        print("✅ Все колонки добавлены!")
else:
    print("✅ Колонки уже есть!")

print("✅ Миграция завершена!")
