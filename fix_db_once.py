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

with get_db() as conn:
    cursor = conn.cursor()
    
    if 'tokens' not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN tokens INTEGER DEFAULT 0")
        print("✅ Добавлена колонка tokens")
    else:
        print("⏭️ Колонка tokens уже есть")
    
    if 'trial_start' not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN trial_start TEXT")
        print("✅ Добавлена колонка trial_start")
    else:
        print("⏭️ Колонка trial_start уже есть")
    
    if 'text_requests' not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN text_requests INTEGER DEFAULT 0")
        print("✅ Добавлена колонка text_requests")
    else:
        print("⏭️ Колонка text_requests уже есть")
    
    if 'max_text_requests' not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN max_text_requests INTEGER DEFAULT 10")
        print("✅ Добавлена колонка max_text_requests")
    else:
        print("⏭️ Колонка max_text_requests уже есть")
    
    if 'text_requests_reset' not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN text_requests_reset TEXT")
        print("✅ Добавлена колонка text_requests_reset")
    else:
        print("⏭️ Колонка text_requests_reset уже есть")

print("✅ Миграция завершена!")
