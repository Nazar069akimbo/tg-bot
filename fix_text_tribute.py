import os
import re

path = "handlers/text.py"
if not os.path.exists(path):
    print("❌ Файл не найден")
    exit(1)

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Добавляем "waiting_tribute_link" в список состояний
if '"waiting_tribute_link"' not in content:
    # Ищем конец списка состояний
    old_list = '"waiting_price_add",\n        "waiting_backup_time",'
    new_list = '"waiting_price_add",\n        "waiting_backup_time",\n        "waiting_tribute_link",'
    
    if old_list in content:
        content = content.replace(old_list, new_list)
        print("✅ Добавлено 'waiting_tribute_link' в список состояний")
    else:
        # Если список выглядит иначе, ищем просто waiting_backup_time
        content = content.replace('"waiting_backup_time",', '"waiting_backup_time",\n        "waiting_tribute_link",')
        print("✅ Добавлено 'waiting_tribute_link' (альтернативный метод)")

# 2. Добавляем обработчик вызова функции
if 'handle_tribute_link' not in content:
    # Ищем место перед обработкой цены (waiting_price_edit)
    old_block = '''        elif state_name == "waiting_backup_time":
            from .admin.backup_settings import handle_backup_time
            await handle_backup_time(message)
            return'''
    
    new_block = '''        elif state_name == "waiting_backup_time":
            from .admin.backup_settings import handle_backup_time
            await handle_backup_time(message)
            return
            
        elif state_name == "waiting_tribute_link":
            from .admin.prices import handle_tribute_link
            await handle_tribute_link(message)
            return'''
    
    if old_block in content:
        content = content.replace(old_block, new_block)
        print("✅ Добавлен вызов handle_tribute_link")
    else:
        print("⚠️ Не удалось найти блок waiting_backup_time для вставки.")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("🎉 Готово! Теперь делай git push.")
