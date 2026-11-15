import os
import re

path = "handlers/payments.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

pattern = r"async def buy_tokens_screen\(callback=None, message=None\):.*?(?=@router\.message\(Command\(\"credits\"\)\))"

new_func = '''async def buy_tokens_screen(callback=None, message=None):
    user_id = (callback.from_user.id if callback else message.from_user.id)
    prem = is_premium(user_id)
    tariffs = get_tariffs("tokens")
    kb_rows = []
    
    text = "🛒 Купить токены\\n\\n"
    if prem:
        text += "💎 <b>У тебя Premium! Скидка 20% на все пакеты!</b>\\n\\n"
    
    for t in tariffs:
        link = t.get('tribute_link')
        
        price = t['price_rub']
        if prem:
            price = int(price * 0.8)
            
        if link:
            kb_rows.append([InlineKeyboardButton(
                text=f"{t['name']} — {price}₽" + (f" (вместо {t['price_rub']}₽)" if prem else ""),
                url=link
            )])
        else:
            kb_rows.append([InlineKeyboardButton(
                text=f"{t['name']} — {price}₽ ({t['stars']} ⭐)",
                callback_data=f"buy_tariff_{t['id']}"
            )])
            
        text += f"• {t['name']} — {price}₽ = {t['tokens']} токенов\\n"
        
    kb_rows.append([InlineKeyboardButton(text="💎 Подписки", callback_data="subscription")])
    kb_rows.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
        
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
    print("✅ handlers/payments.py обновлен (скидка 20%)")
else:
    print("⚠️ Не удалось найти buy_tokens_screen в payments.py")
