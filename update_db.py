from database.db import get_db

with get_db() as conn:
    cursor = conn.cursor()
    
    # Добавляем колонки в users
    cursor.execute("PRAGMA table_info(users)")
    existing = [row[1] for row in cursor.fetchall()]
    
    new_cols = {
        'tokens': 'INTEGER DEFAULT 0',
        'trial_start': 'TEXT',
        'text_requests': 'INTEGER DEFAULT 0',
        'max_text_requests': 'INTEGER DEFAULT 10',
        'text_requests_reset': 'TEXT'
    }
    
    for col, dtype in new_cols.items():
        if col not in existing:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {dtype}")
            print(f"✅ Добавлена колонка {col}")
    
    # Добавляем plan в payments если нет
    cursor.execute("PRAGMA table_info(payments)")
    payment_cols = [row[1] for row in cursor.fetchall()]
    if 'plan' not in payment_cols:
        cursor.execute("ALTER TABLE payments ADD COLUMN plan TEXT")
        print("✅ Добавлена колонка plan в payments")
    
    print("✅ База данных обновлена!")
