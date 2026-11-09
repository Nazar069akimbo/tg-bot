import sqlite3
import os

DB_PATH = 'data/repsolver.db'
if not os.path.exists(DB_PATH):
    print("❌ БД не найдена. Пропускаю.")
else:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE tariffs ADD COLUMN tribute_link TEXT DEFAULT ''")
        print("✅ Колонка tribute_link успешно добавлена в таблицу tariffs.")
    except sqlite3.OperationalError as e:
        print(f"ℹ️ Колонка уже существует или ошибка: {e}")
    conn.commit()
    conn.close()
