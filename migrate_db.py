from database.db import get_db

with get_db() as conn:
    cursor = conn.cursor()
    
    # Добавляем колонки в users
    cursor.execute("PRAGMA table_info(users)")
    existing = [row[1] for row in cursor.fetchall()]
    
    for col in ['watermark_off', 'trial_active', 'trial_start']:
        if col not in existing:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {'INTEGER DEFAULT 0' if col != 'trial_start' else 'TEXT'}")
            print(f"✅ Добавлена колонка {col}")
    
    print("✅ База данных обновлена!")
