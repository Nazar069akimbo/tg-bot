import sqlite3
import os

DB_PATH = 'data/repsolver.db'

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Проверяем promocodes
    cursor.execute("PRAGMA table_info(promocodes)")
    cols = [row[1] for row in cursor.fetchall()]
    
    print(f"📋 Существующие колонки: {cols}")
    
    if 'bonus_tokens' not in cols:
        cursor.execute("ALTER TABLE promocodes ADD COLUMN bonus_tokens INTEGER DEFAULT 0")
        print("✅ Добавлена bonus_tokens")
    
    if 'bonus_images' not in cols:
        cursor.execute("ALTER TABLE promocodes ADD COLUMN bonus_images INTEGER DEFAULT 0")
        print("✅ Добавлена bonus_images")
    
    if 'bonus_requests' not in cols:
        cursor.execute("ALTER TABLE promocodes ADD COLUMN bonus_requests INTEGER DEFAULT 0")
        print("✅ Добавлена bonus_requests")
    
    if 'max_uses' not in cols:
        cursor.execute("ALTER TABLE promocodes ADD COLUMN max_uses INTEGER DEFAULT 1")
        print("✅ Добавлена max_uses")
    
    if 'used' not in cols:
        cursor.execute("ALTER TABLE promocodes ADD COLUMN used INTEGER DEFAULT 0")
        print("✅ Добавлена used")
    
    conn.commit()
    conn.close()
    print("✅ База данных обновлена!")

if __name__ == "__main__":
    migrate()
