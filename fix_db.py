import re

path = "database/db.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Меняем таймер с 10 секунд на 180 (3 минуты)
content = content.replace("_db_backup_timer = threading.Timer(10, _do_db_backup)", "_db_backup_timer = threading.Timer(180, _do_db_backup)")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("✅ database/db.py обновлен (бэкап БД раз в 3 минуты вместо 10 секунд)")
