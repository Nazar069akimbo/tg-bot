import os
import re

path = "handlers/admin/users.py"
if not os.path.exists(path):
    print("❌ Файл не найден")
    exit(1)

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Исправляем toggle_block
old_toggle = '''    uid = int(callback.data.split("|")[1])
    user = get_user(uid)
    if user.get('is_blocked'):
        unblock_user(uid)
        await helpers.safe_answer(callback, "✅ Полностью разблокирован", show_alert=True)
    else:
        block_user(uid)
        await helpers.safe_answer(callback, "✅ Полностью заблокирован (доступна только поддержка)", show_alert=True)'''

new_toggle = '''    uid = int(callback.data.split("|")[1])
    user = get_user(uid)
    if not user:
        await helpers.safe_answer(callback, "❌ Юзер не найден", show_alert=True)
        return
    user = dict(user)
    if user.get('is_blocked'):
        unblock_user(uid)
        await helpers.safe_answer(callback, "✅ Полностью разблокирован", show_alert=True)
    else:
        block_user(uid)
        await helpers.safe_answer(callback, "✅ Полностью заблокирован (доступна только поддержка)", show_alert=True)'''

content = content.replace(old_toggle, new_toggle)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("✅ handlers/admin/users.py исправлен (добавлен dict(user))")
