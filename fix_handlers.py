import re

with open('handlers.py', 'r') as f:
    content = f.read()

# Находим функцию start_cmd и перезаписываем её правильно
pattern = r'@router\.message\(Command\("start"\)\)\s+async def start_cmd\(message: types\.Message\):.*?(?=\n@router\.message)'
match = re.search(pattern, content, re.DOTALL)

if match:
    old_func = match.group(0)
    
    new_func = '''@router.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    user = force_create_user(user_id, username)
    if not user:
        await message.answer("❌ Ошибка регистрации.")
        return
    if not user['username'] or user['username'] == str(user_id):
        user_pages[user_id] = {"state": "waiting_name"}
        await message.answer("👋 Привет! Как мне тебя называть?\\nНапиши своё имя:")
        return
    args = message.text.split() if message.text else []
    if len(args) > 1 and args[1].isdigit():
        referrer_id = int(args[1])
        if referrer_id != user_id:
            success, msg = add_referral(referrer_id, user_id)
            if success:
                await message.answer(msg)
    text = (
        "🤖 **Vertex AI**\\n\\n"
        "Искусственный интеллект в Telegram!\\n\\n"
        "🔴 Бесплатно: 10 запросов/день + 3 картинки\\n"
        "💎 Premium: безлимит + 50 картинок/день (49⭐/мес)\\n"
        "👑 Premium Deluxe: безлимит + 200 картинок/день (99⭐/мес)\\n\\n"
        "📅 Ежедневный бонус: нажми 'Бонус дня'\\n"
        "👥 Приведи друга: +3 картинки и +10 запросов\\n\\n"
        "✏️ Просто напиши свой вопрос!"
    )
    await message.answer(text, reply_markup=main_menu())'''
    
    content = content.replace(old_func, new_func)
    
    with open('handlers.py', 'w') as f:
        f.write(content)
    
    print("✅ start_cmd полностью исправлен!")
else:
    print("❌ Функция start_cmd не найдена")
