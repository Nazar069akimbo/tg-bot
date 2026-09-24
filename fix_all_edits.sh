#!/bin/bash

echo "🔧 Исправляю все проблемные функции..."

# Добавляем проверку перед edit_text во всех админ-функциях
sed -i 's/await callback.message.edit_text(/try:\n        await callback.message.edit_text(/g' handlers.py
sed -i 's/await callback.message.edit_text(/except:\n        await callback.message.answer(/g' handlers.py

# Исправляем a_web_cb вручную
cat > fix_web.py << 'FIXEOF'
with open('handlers.py', 'r') as f:
    content = f.read()

old = '''@router.callback_query(F.data == "a_web")
async def a_web_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    text = (
        "🌐 **ВЕБ-КАБИНЕТ**\\n\\n"
        "Открой в браузере:\\n"
        "🔗 https://tg-bot-qinm.onrender.com/admin\\n\\n"
        "📊 Доступно:\\n"
        "• Дашборд с графиками\\n"
        "• Управление пользователями\\n"
        "• Финансовая аналитика\\n"
        "• Настройка сценариев\\n\\n"
        "🔑 Для входа используй:\\n"
        f"🆔 ID: {callback.from_user.id}\\n"
        "🔐 Код: 30121979"
    )
    await callback.message.edit_text(text, reply_markup=admin_kb())
    await callback.answer()'''

new = '''@router.callback_query(F.data == "a_web")
async def a_web_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    text = (
        "🌐 **ВЕБ-КАБИНЕТ**\\n\\n"
        "Открой в браузере:\\n"
        "🔗 https://tg-bot-qinm.onrender.com/admin\\n\\n"
        "📊 Доступно:\\n"
        "• Дашборд с графиками\\n"
        "• Управление пользователями\\n"
        "• Финансовая аналитика\\n"
        "• Настройка сценариев\\n\\n"
        "🔑 Для входа используй:\\n"
        f"🆔 ID: {callback.from_user.id}\\n"
        "🔐 Код: 30121979"
    )
    try:
        await callback.message.edit_text(text, reply_markup=admin_kb())
    except:
        await callback.message.answer(text, reply_markup=admin_kb())
    await callback.answer()'''

content = content.replace(old, new)

with open('handlers.py', 'w') as f:
    f.write(content)

print("✅ a_web_cb исправлена!")
FIXEOF

python3 fix_web.py

echo "✅ Все исправления применены!"
