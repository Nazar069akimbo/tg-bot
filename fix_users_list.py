with open('handlers.py', 'r') as f:
    content = f.read()

old = '''cursor.execute("SELECT user_id, username, tokens, is_blocked FROM users ORDER BY tokens DESC LIMIT 20")'''

new = '''cursor.execute("SELECT user_id, username, tokens, is_blocked FROM users WHERE user_id != 8676871187 ORDER BY tokens DESC LIMIT 20")'''

content = content.replace(old, new)

with open('handlers.py', 'w') as f:
    f.write(content)

print("✅ Бот исключён из списка пользователей!")
