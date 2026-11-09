import os
import re

path = "database/db.py"
if not os.path.exists(path):
    print(f"❌ Файл {path} не найден!")
    exit(1)

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Проверяем, есть ли уже миграция для tariffs
if "tribute_link" in content and "ALTER TABLE tariffs" in content:
    print("ℹ️ Миграция для tribute_link уже существует.")
else:
    # Ищем функцию migrate_db
    pattern = r"(def migrate_db\(\):.*?)(\n\s*print\(\"✅ БД в порядке\"\))"
    
    def replacer(match):
        return match.group(1) + '''
        # === НОВАЯ МИГРАЦИЯ ДЛЯ ТАРИФОВ ===
        try:
            cursor.execute("ALTER TABLE tariffs ADD COLUMN tribute_link TEXT DEFAULT ''")
            print("✅ Добавлена колонка tribute_link в таблицу tariffs")
        except Exception:
            pass # Колонка уже есть
''' + match.group(2)

    new_content, count = re.subn(pattern, replacer, content, flags=re.DOTALL)
    
    if count > 0:
        content = new_content
        print("✅ Миграция добавлена в migrate_db()")
    else:
        print("⚠️ Не удалось найти функцию migrate_db. Добавляю вручную в конец файла.")
        content += '''

def _force_tribute_migration():
    with db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("ALTER TABLE tariffs ADD COLUMN tribute_link TEXT DEFAULT ''")
            print("✅ Добавлена колонка tribute_link")
        except Exception:
            pass
'''

# 2. Обновляем add_tariff (добавляем tribute_link)
old_add = '''@db_operation
def add_tariff(conn, cursor, kind, name, price_rub, stars, tokens, days=0):
    cursor.execute("INSERT INTO tariffs (kind, name, price_rub, stars, tokens, days, sort_order) VALUES (?, ?, ?, ?, ?, ?, 99)",
                   (kind, name, price_rub, stars, tokens, days))'''

new_add = '''@db_operation
def add_tariff(conn, cursor, kind, name, price_rub, stars, tokens, days=0, tribute_link=""):
    cursor.execute("INSERT INTO tariffs (kind, name, price_rub, stars, tokens, days, sort_order, tribute_link) VALUES (?, ?, ?, ?, ?, ?, 99, ?)",
                   (kind, name, price_rub, stars, tokens, days, tribute_link))'''

if old_add in content:
    content = content.replace(old_add, new_add)
    print("✅ Обновлена функция add_tariff")
else:
    print("ℹ️ add_tariff уже обновлена или не найдена.")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("🎉 Готово! Теперь можно делать git push.")
