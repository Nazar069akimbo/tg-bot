from database.db import get_db

with get_db() as conn:
    cursor = conn.cursor()
    
    # Добавляем колонку tokens в users
    cursor.execute("PRAGMA table_info(users)")
    existing = [row[1] for row in cursor.fetchall()]
    
    if 'tokens' not in existing:
        cursor.execute("ALTER TABLE users ADD COLUMN tokens INTEGER DEFAULT 0")
        print("✅ Добавлена колонка tokens в users")
    
    if 'trial_start' not in existing:
        cursor.execute("ALTER TABLE users ADD COLUMN trial_start TEXT")
        print("✅ Добавлена колонка trial_start в users")
    
    # Добавляем колонку plan в payments (если нет)
    cursor.execute("PRAGMA table_info(payments)")
    payment_cols = [row[1] for row in cursor.fetchall()]
    if 'plan' not in payment_cols:
        cursor.execute("ALTER TABLE payments ADD COLUMN plan TEXT")
        print("✅ Добавлена колонка plan в payments")
    
    print("✅ База данных обновлена!")
