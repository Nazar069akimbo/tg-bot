import os
import re

# ==========================================
# 1. Исправляем handlers/text.py
# ==========================================
text_path = "handlers/text.py"
if os.path.exists(text_path):
    with open(text_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Проверяем, есть ли уже обработка waiting_admin_reply_to_user
    if "waiting_admin_reply_to_user" not in content or "target_user_id" not in content:
        # Ищем место, куда вставить (перед # ПРОМОКОД)
        insert_code = """
    if state_name == "waiting_admin_reply_to_user":
        target_id = state.get("target_user_id")
        if not target_id:
            helpers.user_pages.pop(user_id, None)
            await message.answer("❌ Ошибка: цель не найдена", reply_markup=helpers.admin_kb())
            return
            
        safe_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Ответить", callback_data=f"reply_to_ticket|admin")]
        ])
        try:
            await message.bot.send_message(
                target_id,
                f"🛡 <b>Сообщение от поддержки:</b>\\n\\n{safe_text}",
                reply_markup=kb
            )
            await message.answer("✅ Сообщение отправлено юзеру!", reply_markup=helpers.admin_kb())
        except Exception as e:
            logger.error(f"❌ Не отправил юзеру: {e}")
            await message.answer(f"❌ Ошибка отправки: {e}", reply_markup=helpers.admin_kb())
            
        helpers.user_pages.pop(user_id, None)
        return

    # 4. ПРОМОКОД
"""
        content = content.replace("    # 4. ПРОМОКОД\n", insert_code)
        
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(content)
        print("✅ handlers/text.py исправлен (добавлена отправка сообщения юзеру)")
    else:
        print("ℹ️ handlers/text.py уже содержит обработку отправки")
else:
    print("❌ handlers/text.py не найден")


# ==========================================
# 2. Исправляем handlers/admin/menu.py (Баланс Stars)
# ==========================================
menu_path = "handlers/admin/menu.py"
if os.path.exists(menu_path):
    with open(menu_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Регулярное выражение для поиска функции a_stars_balance_cb
    pattern = r"@router\.callback_query\(F\.data == \"a_stars_balance\"\).*?(?=@router\.callback_query|\Z)"
    
    new_func = '''@router.callback_query(F.data == "a_stars_balance")
async def a_stars_balance_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    
    balance = None
    try:
        if hasattr(callback.bot, "get_my_star_balance"):
            balance = await callback.bot.get_my_star_balance()
    except Exception:
        pass

    stars30, count30 = get_payments_summary(days=30)
    rub30 = stars30 * 0.45

    if balance is not None:
        rub_api = balance * 0.45
        api_line = f"💳 Баланс бота: <b>{balance} ⭐</b>\\n💵 ≈ {rub_api:.2f} ₽"
    else:
        api_line = (
            "🔌 API: <i>недоступен (нужна новая версия aiogram)</i>\\n"
            "💡 Точный баланс: @BotFather → /mybots → Stars"
        )

    text = (
        "⭐ <b>БАЛАНС STARS</b>\\n\\n"
        f"{api_line}\\n\\n"
        "📊 <b>За последние 30 дней</b>\\n"
        f"💰 Оплачено: <b>{stars30} ⭐</b>\\n"
        f"🧾 Платежей: <b>{count30}</b>\\n"
        f"💵 ≈ {rub30:.2f} ₽"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧾 Последние платежи", callback_data="a_payments_list")],
        [back_btn("admin_panel")]
    ])
    await safe_edit(callback, text, kb)
    await helpers.safe_answer(callback)

'''
    if "@router.callback_query(F.data == \"a_stars_balance\")" in content:
        # Заменяем старую функцию на новую
        content = re.sub(pattern, new_func, content, flags=re.DOTALL)
        with open(menu_path, "w", encoding="utf-8") as f:
            f.write(content)
        print("✅ handlers/admin/menu.py исправлен (обновлена функция Баланса Stars)")
    else:
        print("⚠️ Функция a_stars_balance не найдена в handlers/admin/menu.py")
else:
    print("❌ handlers/admin/menu.py не найден")

print("🎉 Готово! Теперь сделай: git add . && git commit -m 'fix admin' && git push")
