import os
import re

path = "handlers/payments.py"
if not os.path.exists(path):
    print("❌ Файл payments.py не найден")
    exit(1)

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Ищем функцию buy_tokens_screen и заменяем её целиком
pattern = r"async def buy_tokens_screen\(callback=None, message=None\):.*?(?=@router\.message\(Command\(\"credits\"\)\)|\Z)"

new_func = '''async def buy_tokens_screen(callback=None, message=None):
    user_id = (callback.from_user.id if callback else message.from_user.id)
    prem = is_premium(user_id)
    tariffs = get_tariffs("tokens")
    kb_rows = []
    
    for t in tariffs:
        # Берем ссылку из базы данных
        link = t.get('tribute_link')
        
        if link:
            # Если ссылка есть — ведем на Tribute
            kb_rows.append([InlineKeyboardButton(
                text=f"{t['name']} — {t['price_rub']}₽",
                url=link
            )])
        else:
            # Если ссылки нет — показываем кнопку Stars (как раньше)
            kb_rows.append([InlineKeyboardButton(
                text=f"{t['name']} — {t['price_rub']}₽ ({t['stars']} ⭐)",
                callback_data=f"buy_tariff_{t['id']}"
            )])
            
    kb_rows.append([InlineKeyboardButton(text="💎 Подписки", callback_data="subscription")])
    kb_rows.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    
    text = "🛒 Купить токены\\n\\n"
    if prem:
        text += "💎 У тебя Premium!\\n"
    for t in tariffs:
        text += f"• {t['name']} — {t['price_rub']}₽ = {t['tokens']} токенов\\n"
        
    if callback:
        try:
            await callback.message.edit_text(text, reply_markup=kb)
        except Exception:
            await callback.message.answer(text, reply_markup=kb)
        await helpers.safe_answer(callback)
    else:
        await message.answer(text, reply_markup=kb)

'''

new_content, count = re.subn(pattern, new_func, content, flags=re.DOTALL)

if count > 0:
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("✅ Функция buy_tokens_screen обновлена! Теперь она проверяет ссылку Tribute.")
else:
    print("⚠️ Не удалось найти функцию buy_tokens_screen. Возможно, она уже изменена.")
