from database.db import get_db

with get_db() as conn:
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(users)")
    existing = [row[1] for row in cursor.fetchall()]
    
    if 'tokens' not in existing:
        cursor.execute("ALTER TABLE users ADD COLUMN tokens INTEGER DEFAULT 0")
        print("✅ Добавлена колонка tokens")
    
    if 'trial_start' not in existing:
        cursor.execute("ALTER TABLE users ADD COLUMN trial_start TEXT")
        print("✅ Добавлена колонка trial_start")
    
    print("✅ База данных обновлена!")
