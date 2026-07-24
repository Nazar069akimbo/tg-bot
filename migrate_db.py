from database.db import get_db

print("🔄 Обновление базы данных...")

with get_db() as conn:
    cursor = conn.cursor()
    
    # 1. Таблица промокодов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS promocodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        bonus_images INTEGER DEFAULT 0,
        bonus_requests INTEGER DEFAULT 0,
        max_uses INTEGER DEFAULT 1,
        used INTEGER DEFAULT 0,
        created_by INTEGER,
        created_at TEXT,
        expires_at TEXT
    )
    ''')
    print("✅ Таблица promocodes")
    
    # 2. Использования промокодов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS promocode_uses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        promocode_id INTEGER,
        user_id INTEGER,
        used_at TEXT,
        FOREIGN KEY (promocode_id) REFERENCES promocodes(id)
    )
    ''')
    print("✅ Таблица promocode_uses")
    
    # 3. Журнал админа
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admin_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER,
        action TEXT,
        target_id INTEGER,
        details TEXT,
        timestamp TEXT
    )
    ''')
    print("✅ Таблица admin_log")
    
    # 4. Добавляем колонки в users
    cursor.execute("PRAGMA table_info(users)")
    existing_cols = [row[1] for row in cursor.fetchall()]
    
    new_cols = {
        'last_active': 'TEXT',
        'total_spent': 'INTEGER DEFAULT 0'
    }
    
    for col, dtype in new_cols.items():
        if col not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {dtype}")
                print(f"✅ Добавлена колонка {col}")
            except:
                pass
    
    # 5. Добавляем колонку plan в payments если нет
    cursor.execute("PRAGMA table_info(payments)")
    payment_cols = [row[1] for row in cursor.fetchall()]
    if 'plan' not in payment_cols:
        try:
            cursor.execute("ALTER TABLE payments ADD COLUMN plan TEXT")
            print("✅ Добавлена колонка plan в payments")
        except:
            pass
    
    print("")
    print("✅ База данных успешно обновлена!")
