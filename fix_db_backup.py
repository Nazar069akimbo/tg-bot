import re
import os

path = "database/db.py"

if not os.path.exists(path):
    print(f"❌ Файл {path} не найден!")
    exit(1)

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Ищем старую функцию _schedule_db_backup и всё, что внутри неё
# (от def _schedule_db_backup() до def _do_db_backup() или другой функции)
pattern = r"def _schedule_db_backup\(\):.*?(?=def _do_db_backup\(\)|@contextmanager|def init_db|$)"

new_func = '''def _schedule_db_backup():
    # ОТКЛЮЧЕНО для экономии трафика Render.
    # Бэкап базы данных делается строго в 05:00 через bot.py
    pass

'''

new_content, count = re.subn(pattern, new_func, content, flags=re.DOTALL)

if count > 0:
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"✅ Успешно! Функция _schedule_db_backup отключена в {path}")
    print("Теперь база данных не будет сохраняться при каждом изменении.")
else:
    print("⚠️ Функция _schedule_db_backup не найдена. Возможно, она уже отключена.")
