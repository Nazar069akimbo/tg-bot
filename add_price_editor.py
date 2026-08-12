with open('handlers.py', 'r') as f:
    content = f.read()

# Добавляем функцию для редактирования цен
price_editor = '''

# ===== УПРАВЛЕНИЕ ЦЕНАМИ =====
@router.callback_query(F.data == "a_edit_prices")
async def a_edit_prices_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for key, model in IMAGE_MODELS.items():
        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{model['name']} — {model['price']} токенов",
                callback_data=f"edit_price_{key}"
            )
        ])
    kb.inline_keyboard.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")
    ])
    
    await callback.message.edit_text(
        "💰 **Управление ценами**\\n\\n"
        "Выбери модель для изменения цены:",
        reply_markup=kb
    )
    await callback.answer()

@router.callback_query(F.data.startswith("edit_price_"))
async def edit_price_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    model_key = callback.data.replace("edit_price_", "")
    model = IMAGE_MODELS[model_key]
    user_pages[callback.from_user.id] = {"state": "waiting_price", "model": model_key}
    
    await callback.message.edit_text(
        f"💰 **Изменение цены**\\n\\n"
        f"Модель: {model['name']}\\n"
        f"Текущая цена: {model['price']} токенов\\n\\n"
        f"Введи **новую цену** в токенах:\\n"
        f"(например: `15`)\\n\\n"
        f"⏹ /cancel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="a_edit_prices")]
        ])
    )
    await callback.answer()
'''

# Вставляем price_editor перед последней функцией
content = content.replace('async def handle_admin_input', price_editor + '\nasync def handle_admin_input')

# Добавляем обработку ввода цены в handle_admin_input
old_input = '    if state.get("state") == "waiting_give_tokens":'
new_input = '''    if state.get("state") == "waiting_price":
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

content = content.replace(old_input, new_input)

# Добавляем кнопку в админ-панель
old_admin = '''    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="a_stats"), InlineKeyboardButton(text="📈 Модели", callback_data="a_model_stats")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="a_users"), InlineKeyboardButton(text="⭐ Раздать токены", callback_data="a_give_tokens")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="a_broadcast"), InlineKeyboardButton(text="🚫 Блокировка", callback_data="a_block")],
        [InlineKeyboardButton(text="💾 Бэкап", callback_data="a_backup"), InlineKeyboardButton(text="📩 Обращения", callback_data="a_messages")],
        [InlineKeyboardButton(text="📤 Выгрузить БД", callback_data="a_export_db"), InlineKeyboardButton(text="📥 Восстановить из GitHub", callback_data="a_restore_github")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])'''

new_admin = '''    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="a_stats"), InlineKeyboardButton(text="📈 Модели", callback_data="a_model_stats")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="a_users"), InlineKeyboardButton(text="⭐ Раздать токены", callback_data="a_give_tokens")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="a_broadcast"), InlineKeyboardButton(text="🚫 Блокировка", callback_data="a_block")],
        [InlineKeyboardButton(text="💾 Бэкап", callback_data="a_backup"), InlineKeyboardButton(text="📩 Обращения", callback_data="a_messages")],
        [InlineKeyboardButton(text="📤 Выгрузить БД", callback_data="a_export_db"), InlineKeyboardButton(text="📥 Восстановить из GitHub", callback_data="a_restore_github")],
        [InlineKeyboardButton(text="💰 Цены", callback_data="a_edit_prices"), InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])'''

content = content.replace(old_admin, new_admin)

with open('handlers.py', 'w') as f:
    f.write(content)

print("✅ Добавлено управление ценами в админке!")
