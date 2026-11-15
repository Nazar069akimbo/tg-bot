import os
import re

path = "database/db.py"
if not os.path.exists(path):
    print("❌ Файл не найден")
    exit(1)

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Добавляем таблицу в init_db()
if "CREATE TABLE IF NOT EXISTS tribute_transactions" not in content:
    # Ищем место перед созданием таблицы warnings
    target = "cursor.execute('''\n        CREATE TABLE IF NOT EXISTS warnings ("
    table_sql = """cursor.execute('''
        CREATE TABLE IF NOT EXISTS tribute_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_id TEXT UNIQUE,
            user_id INTEGER,
            product_name TEXT,
            tokens_added INTEGER,
            created_at TEXT
        )
        ''')

        """
    if target in content:
        content = content.replace(target, table_sql + target)
        print("✅ Таблица tribute_transactions добавлена в init_db")
    else:
        print("⚠️ Не найдено место для вставки таблицы, добавляю в конец init_db")
        # Резервный вариант - ищем print("✅ База данных инициализирована")
        content = content.replace('print("✅ База данных инициализирована")', table_sql + '\n        print("✅ База данных инициализирована")')

# 2. Добавляем функции в конец файла
if "def check_tribute_transaction" not in content:
    funcs = '''

# === ФУНКЦИИ ДЛЯ TRIBUTE WEBHOOK ===
@db_operation
def check_tribute_transaction(conn, cursor, tx_id):
    cursor.execute("SELECT id FROM tribute_transactions WHERE tx_id = ?", (tx_id,))
    return cursor.fetchone() is not None

@db_operation
def add_tribute_transaction(conn, cursor, tx_id, user_id, product_name, tokens_added):
    cursor.execute(
        "INSERT INTO tribute_transactions (tx_id, user_id, product_name, tokens_added, created_at) VALUES (?, ?, ?, ?, ?)",
        (tx_id, user_id, product_name, tokens_added, datetime.now().isoformat())
    )
    _schedule_db_backup()
'''
    content += funcs
    print("✅ Функции для Tribute добавлены в конец db.py")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("🎉 database/db.py обновлен!")
