import sqlite3

DB_PATH = 'data/repsolver.db'

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Проверяем и добавляем колонки в users
cursor.execute("PRAGMA table_info(users)")
cols = [row[1] for row in cursor.fetchall()]

new_cols = {
    'tokens': 'INTEGER DEFAULT 0',
    'trial_start': 'TEXT',
    'text_requests': 'INTEGER DEFAULT 0',
    'max_text_requests': 'INTEGER DEFAULT 10',
    'text_requests_reset': 'TEXT'
}

for col, dtype in new_cols.items():
    if col not in cols:
        cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {dtype}")
        print(f"✅ Добавлена колонка {col}")

# Проверяем payments
cursor.execute("PRAGMA table_info(payments)")
payment_cols = [row[1] for row in cursor.fetchall()]
if 'plan' not in payment_cols:
    cursor.execute("ALTER TABLE payments ADD COLUMN plan TEXT")
    print("✅ Добавлена колонка plan в payments")

conn.commit()
conn.close()

print("✅ Миграция выполнена!")
