import os
import re

path = "handlers/image.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Меняем блок с водяным знаком
pattern_wm = r"# Водяной знак.*?(?=# Сохранение)"
new_wm = '''# Водяной знак
        try:
            img = Image.open(BytesIO(img_data)).convert("RGBA")
            draw = ImageDraw.Draw(img)
            
            no_wm = has_no_watermark(user_id)
            
            if no_wm:
                font_size = 10
                text_wm = "Vertex AI"
            else:
                font_size = 40
                text_wm = "Vertex AI (Купи Premium)"

            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
            except Exception:
                font = ImageFont.load_default()
                
            draw.text((10, 10), text_wm, font=font, fill=(255, 255, 255, 200))
            
            output = BytesIO()
            img.convert("RGB").save(output, format='PNG')
            output.seek(0)
            img_data = output.getvalue()
        except Exception as e:
            logger.warning(f"⚠️ [{user_id}] Водяной знак: {e}")

        '''
content = re.sub(pattern_wm, new_wm, content, flags=re.DOTALL)

# 2. Меняем клавиатуру под картинкой
pattern_kb = r"keyboard = InlineKeyboardMarkup\(inline_keyboard=\[.*?\]\)"
new_kb = '''keyboard_rows = []
        if not has_no_watermark(user_id):
            keyboard_rows.append([InlineKeyboardButton(text="✨ Убрать водяной знак (10 токенов)", callback_data="buy_no_watermark")])
            keyboard_rows.append([InlineKeyboardButton(text="💎 Купить Premium (без знака навсегда)", callback_data="subscription")])
        keyboard_rows.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)'''
content = re.sub(pattern_kb, new_kb, content, flags=re.DOTALL)

# 3. Добавляем обработчик кнопки в конец
if "buy_no_watermark_cb" not in content:
    handler = '''

@router.callback_query(F.data == "buy_no_watermark")
async def buy_no_watermark_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if has_no_watermark(user_id):
        await helpers.safe_answer(callback, "✅ У тебя уже нет водяного знака!", show_alert=True)
        return
        
    if get_tokens(user_id) < 10:
        await helpers.safe_answer(callback, "❌ Не хватает токенов (нужно 10).", show_alert=True)
        return
        
    spend_tokens(user_id, 10)
    buy_no_watermark(user_id)
    await helpers.safe_answer(callback, "✅ Водяной знак убран! Следующие картинки будут без него.", show_alert=True)
'''
    content += handler

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("✅ handlers/image.py обновлен (водяной знак и кнопки)")
