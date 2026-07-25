from database.db import get_db

with get_db() as conn:
    cursor = conn.cursor()
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
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS promocode_uses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        promocode_id INTEGER,
        user_id INTEGER,
        used_at TEXT
    )
    ''')
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
    print("✅ Таблицы созданы")
