from database.db import get_db

with get_db() as conn:
    cursor = conn.cursor()
    
    # Проверяем, есть ли колонка tokens
    cursor.execute("PRAGMA table_info(users)")
    cols = [row[1] for row in cursor.fetchall()]
    
    if 'tokens' not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN tokens INTEGER DEFAULT 0")
        print("✅ Добавлена колонка tokens")
    else:
        print("✅ Колонка tokens уже есть")
    
    if 'trial_start' not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN trial_start TEXT")
        print("✅ Добавлена колонка trial_start")
    
    # Проверяем payments
    cursor.execute("PRAGMA table_info(payments)")
    payment_cols = [row[1] for row in cursor.fetchall()]
    if 'plan' not in payment_cols:
        cursor.execute("ALTER TABLE payments ADD COLUMN plan TEXT")
        print("✅ Добавлена колонка plan в payments")
    
    print("✅ База данных обновлена!")
