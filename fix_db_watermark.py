import sqlite3, os

# 1. Обновляем SQLite базу
DB_PATH = 'data/repsolver.db'
if os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN no_watermark INTEGER DEFAULT 0")
        print("✅ Колонка no_watermark добавлена в БД.")
    except Exception:
        print("ℹ️ Колонка no_watermark уже существует.")
    conn.commit()
    conn.close()

# 2. Добавляем функции в database/db.py
path = "database/db.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

if "def has_no_watermark" not in content:
    funcs = '''

@db_operation
def has_no_watermark(conn, cursor, user_id):
    cursor.execute("SELECT no_watermark, plan FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row: return False
    if row[0] == 1 or row[1] in ('premium', 'premium_plus'):
        return True
    return False

@db_operation
def buy_no_watermark(conn, cursor, user_id):
    cursor.execute("UPDATE users SET no_watermark = 1 WHERE user_id = ?", (user_id,))
    _schedule_db_backup()
'''
    content += funcs
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✅ Функции has_no_watermark и buy_no_watermark добавлены в db.py")
else:
    print("ℹ️ Функции уже есть в db.py")
