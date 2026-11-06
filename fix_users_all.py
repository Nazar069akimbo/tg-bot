import os

path = "handlers/admin/users.py"
if not os.path.exists(path):
    exit(1)

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# В a_user_manage_cb уже есть user = dict(user), так что там ок.
# Проверяем a_user_warn_cb и a_user_soft_block_cb
# В a_user_warn_cb нет вызова user.get(), там просто add_warning
# В a_user_soft_block_cb тоже нет

# Но на всякий случай проверим a_user_manage_cb на наличие user.get() без dict
if "user = dict(user)" not in content:
    print("⚠️ В файле нет 'user = dict(user)', проверь вручную")
else:
    print("✅ В handlers/admin/users.py уже есть конвертация в dict")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
