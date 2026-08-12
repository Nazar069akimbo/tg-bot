with open('handlers.py', 'r') as f:
    content = f.read()

# Находим handle_admin_input и добавляем обработку waiting_price
old = '''async def handle_admin_input(message: types.Message):
    user_id = message.from_user.id
    state = user_pages.get(user_id, {})
    if message.text == "/cancel":
        user_pages.pop(user_id, None)
        await message.answer("✅ Отменено", reply_markup=admin_kb())
        return
    
    if state.get("state") == "waiting_give_tokens":'''

new = '''async def handle_admin_input(message: types.Message):
    user_id = message.from_user.id
    state = user_pages.get(user_id, {})
    if message.text == "/cancel":
        user_pages.pop(user_id, None)
        await message.answer("✅ Отменено", reply_markup=admin_kb())
        return
    
    if state.get("state") == "waiting_price":
        try:
            new_price = int(message.text.strip())
            if new_price < 1:
                await message.answer("❌ Цена должна быть больше 0!", reply_markup=admin_kb())
                return
            model_key = state.get("model")
            if model_key and model_key in IMAGE_MODELS:
                IMAGE_MODELS[model_key]["price"] = new_price
                await message.answer(
                    f"✅ Цена для {IMAGE_MODELS[model_key]['name']} обновлена!\\n"
                    f"💰 Новая цена: {new_price} токенов",
                    reply_markup=admin_kb()
                )
            else:
                await message.answer("❌ Модель не найдена", reply_markup=admin_kb())
        except ValueError:
            await message.answer("❌ Введите число!", reply_markup=admin_kb())
        user_pages.pop(user_id, None)
        return
    
    if state.get("state") == "waiting_give_tokens":'''

content = content.replace(old, new)

with open('handlers.py', 'w') as f:
    f.write(content)

print("✅ Обработчик цен добавлен!")
