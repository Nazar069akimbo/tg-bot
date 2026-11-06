from database.db import db_connection

with db_connection() as conn:
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN is_soft_blocked INTEGER DEFAULT 0")
        print("✅ Колонка is_soft_blocked добавлена")
    except Exception as e:
        print(f"ℹ️ Колонка уже существует или ошибка: {e}")
