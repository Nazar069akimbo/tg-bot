with open('handlers.py', 'r') as f:
    content = f.read()

old = '''@router.callback_query(F.data == "balance")
async def balance_cb(callback: types.CallbackQuery):
    await balance_cmd(callback.message)
    await callback.answer()'''

new = '''@router.callback_query(F.data == "balance")
async def balance_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = force_create_user(user_id, callback.from_user.username or "")
    if not user:
        await callback.answer("❌ Ошибка!", show_alert=True)
        return
    tokens = get_tokens(user_id)
    used, max_req = get_text_requests(user_id)
    trial = get_trial_remaining(user_id)
    text = f"💰 **Баланс**\\n\\n"
    text += f"🪙 Токенов: {tokens}\\n"
    text += f"🖼️ Хватит на: {tokens // 10} картинок\\n"
    text += f"📝 Текст: {used}/{max_req} запросов сегодня\\n"
    if trial > 0:
        text += f"🎁 Пробный период: {trial} дней\\n"
    try:
        await callback.message.edit_text(text, reply_markup=main_menu())
    except:
        await callback.message.answer(text, reply_markup=main_menu())
    await callback.answer()'''

content = content.replace(old, new)

with open('handlers.py', 'w') as f:
    f.write(content)

print("✅ balance_cb исправлен!")
