import re

with open('handlers.py', 'r') as f:
    content = f.read()

# Добавляем функцию получения списка бэкапов из GitHub
get_backup_list_func = '''
def get_backup_list():
    """Получить список бэкапов из GitHub"""
    import requests
    token = os.getenv('GITHUB_TOKEN')
    repo = os.getenv('GITHUB_BACKUP_REPO')
    if not token or not repo:
        return []
    headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
    url = f'https://api.github.com/repos/{repo}/contents/backups'
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return []
    files = [f for f in resp.json() if f['name'].endswith('.db')]
    files.sort(key=lambda x: x['name'], reverse=True)
    return files

def restore_backup_from_github(filename):
    """Восстановить бэкап из GitHub по имени файла"""
    import requests
    import os
    token = os.getenv('GITHUB_TOKEN')
    repo = os.getenv('GITHUB_BACKUP_REPO')
    if not token or not repo:
        return False
    headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
    url = f'https://api.github.com/repos/{repo}/contents/backups/{filename}'
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return False
    file_url = resp.json()['download_url']
    resp = requests.get(file_url)
    if resp.status_code != 200:
        return False
    os.makedirs('data', exist_ok=True)
    with open('data/repsolver.db', 'wb') as f:
        f.write(resp.content)
    return True
'''

content = content + get_backup_list_func

# Добавляем кнопку в admin_kb
old_admin_kb = '''def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="a_stats"), InlineKeyboardButton(text="👥 Пользователи", callback_data="a_users")],
        [InlineKeyboardButton(text="⭐ Раздать токены", callback_data="a_give_tokens"), InlineKeyboardButton(text="📢 Рассылка", callback_data="a_broadcast")],
        [InlineKeyboardButton(text="🚫 Блокировка", callback_data="a_block"), InlineKeyboardButton(text="💾 Бэкап", callback_data="a_backup")],
        [InlineKeyboardButton(text="📩 Обращения", callback_data="a_messages"), InlineKeyboardButton(text="📤 Выгрузить БД", callback_data="a_export_db")],
        [InlineKeyboardButton(text="📥 Восстановить БД", callback_data="a_restore_db")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])'''

new_admin_kb = '''def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="a_stats"), InlineKeyboardButton(text="👥 Пользователи", callback_data="a_users")],
        [InlineKeyboardButton(text="⭐ Раздать токены", callback_data="a_give_tokens"), InlineKeyboardButton(text="📢 Рассылка", callback_data="a_broadcast")],
        [InlineKeyboardButton(text="🚫 Блокировка", callback_data="a_block"), InlineKeyboardButton(text="💾 Бэкап", callback_data="a_backup")],
        [InlineKeyboardButton(text="📩 Обращения", callback_data="a_messages"), InlineKeyboardButton(text="📤 Выгрузить БД", callback_data="a_export_db")],
        [InlineKeyboardButton(text="📥 Восстановить из GitHub", callback_data="a_restore_github")],
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

content = content + export_db_handler

# Добавляем обработчик восстановления из GitHub
restore_github_handler = '''
@router.callback_query(F.data == "a_restore_github")
async def restore_github_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    files = get_backup_list()
    if not files:
        await callback.message.edit_text(
            "❌ Нет бэкапов на GitHub!\\n\\n"
            "Сначала создайте бэкап в админке (кнопка 💾 Бэкап).",
            reply_markup=admin_kb()
        )
        await callback.answer()
        return
    
    # Создаём клавиатуру со списком бэкапов
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for f in files[:20]:  # показываем максимум 20 бэкапов
        # Форматируем дату из имени файла
        name = f['name']
        size_kb = round(f['size'] / 1024, 1)
        label = f"📄 {name[:20]}... ({size_kb} KB)" if len(name) > 20 else f"📄 {name} ({size_kb} KB)"
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=label, callback_data=f"restore_backup_{name}")
        ])
    
    kb.inline_keyboard.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")
    ])
    
    await callback.message.edit_text(
        "📥 **Восстановление из GitHub**\\n\\n"
        "Выберите бэкап для восстановления:\\n"
        f"📦 Всего: {len(files)} бэкапов",
        reply_markup=kb
    )
    await callback.answer()

@router.callback_query(F.data.startswith("restore_backup_"))
async def restore_backup_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    filename = callback.data.replace("restore_backup_", "")
    
    await callback.message.edit_text(
        f"⏳ Восстанавливаю бэкап: `{filename}`...",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="a_restore_github")]
        ])
    )
    
    success = restore_backup_from_github(filename)
    
    if success:
        await callback.message.edit_text(
            f"✅ **Бэкап восстановлен!**\\n\\n"
            f"📄 Файл: `{filename}`\\n"
            f"🔄 Бот перезапущен.",
            reply_markup=admin_kb()
        )
    else:
        await callback.message.edit_text(
            f"❌ **Ошибка восстановления!**\\n\\n"
            f"📄 Файл: `{filename}`\\n"
            f"Попробуйте другой бэкап.",
            reply_markup=admin_kb()
        )
    await callback.answer()
'''

content = content + restore_github_handler

with open('handlers.py', 'w') as f:
    f.write(content)

print("✅ Функция восстановления из GitHub добавлена!")
