with open('handlers.py', 'r') as f:
    content = f.read()

# Обновляем admin_kb
old_admin_kb = '''def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="a_stats"), InlineKeyboardButton(text="👥 Пользователи", callback_data="a_users")],
        [InlineKeyboardButton(text="⭐ Раздать токены", callback_data="a_give_tokens"), InlineKeyboardButton(text="📢 Рассылка", callback_data="a_broadcast")],
        [InlineKeyboardButton(text="🚫 Блокировка", callback_data="a_block"), InlineKeyboardButton(text="💾 Бэкап", callback_data="a_backup")],
        [InlineKeyboardButton(text="📩 Обращения", callback_data="a_messages"), InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])'''

new_admin_kb = '''def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="a_stats"), InlineKeyboardButton(text="👥 Пользователи", callback_data="a_users")],
        [InlineKeyboardButton(text="⭐ Раздать токены", callback_data="a_give_tokens"), InlineKeyboardButton(text="📢 Рассылка", callback_data="a_broadcast")],
        [InlineKeyboardButton(text="🚫 Блокировка", callback_data="a_block"), InlineKeyboardButton(text="💾 Бэкап", callback_data="a_backup")],
        [InlineKeyboardButton(text="📩 Обращения", callback_data="a_messages"), InlineKeyboardButton(text="📤 Выгрузить БД", callback_data="a_export_db")],
        [InlineKeyboardButton(text="📥 Восстановить БД", callback_data="a_restore_db")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])'''

content = content.replace(old_admin_kb, new_admin_kb)

# Добавляем обработчик выгрузки
export_db_handler = '''
@router.callback_query(F.data == "a_export_db")
async def export_db_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    import os
    db_path = "data/repsolver.db"
    if not os.path.exists(db_path):
        await callback.message.edit_text("❌ Файл базы данных не найден!", reply_markup=admin_kb())
        await callback.answer()
        return
    
    try:
        await callback.message.delete()
        await callback.message.answer_document(
            BufferedInputFile(open(db_path, "rb").read(), filename="repsolver.db"),
            caption="📁 **База данных**\\n\\nСкачана в формате SQLite",
            reply_markup=admin_kb()
        )
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {str(e)[:100]}", reply_markup=admin_kb())
    await callback.answer()
'''

# Добавляем обработчик восстановления
restore_db_handler = '''
@router.callback_query(F.data == "a_restore_db")
async def restore_db_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    await callback.message.edit_text(
        "📥 **Восстановление БД**\\n\\n"
        "Пришлите **файл .db** или **.sqlite** в ответ на это сообщение.\\n\\n"
        "⚠️ Восстановление заменит текущую базу данных!\\n"
        "Рекомендую сначала сделать бэкап.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
        ])
    )
    await callback.answer()

@router.message(F.document)
async def restore_db_file(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ Нет доступа")
    
    # Проверяем, что пользователь находится в режиме восстановления
    if user_pages.get(message.from_user.id, {}).get("state") != "waiting_restore_db":
        return
    
    doc = message.document
    if not doc.file_name.endswith(('.db', '.sqlite')):
        return await message.answer("❌ Пожалуйста, отправьте файл .db или .sqlite")
    
    await message.answer("⏳ Восстанавливаю базу данных...")
    
    try:
        # Скачиваем файл
        file = await message.bot.get_file(doc.file_id)
        file_content = await message.bot.download_file(file.file_path)
        
        # Сохраняем в data/repsolver.db
        import os
        os.makedirs("data", exist_ok=True)
        with open("data/repsolver.db", "wb") as f:
            f.write(file_content.read())
        
        # Проверяем, что БД валидна
        import sqlite3
        conn = sqlite3.connect("data/repsolver.db")
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not cursor.fetchone():
            conn.close()
            return await message.answer("❌ Невалидная база данных: таблица users не найдена")
        conn.close()
        
        await message.answer("✅ База данных успешно восстановлена!", reply_markup=admin_kb())
        user_pages.pop(message.from_user.id, None)
        
    except Exception as e:
        await message.answer(f"❌ Ошибка восстановления: {str(e)[:100]}", reply_markup=admin_kb())
'''

# Добавляем обработчики
content = content + export_db_handler + restore_db_handler

with open('handlers.py', 'w') as f:
    f.write(content)

print("✅ Кнопки 'Выгрузить БД' и 'Восстановить БД' добавлены!")
