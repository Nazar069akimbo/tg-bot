import os
import sqlite3

DB_PATH = 'data/repsolver.db'

# 1. Удаляем старую БД
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
    print("🗑️ Старая БД удалена")

# 2. Создаём новую БД с колонками
from database.db import init_db
init_db()
print("✅ Новая БД создана")

# 3. Проверяем колонки
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(users)")
cols = [row[1] for row in cursor.fetchall()]
print(f"📋 Колонки в users: {cols}")
conn.close()
