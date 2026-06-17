from aiogram import Router, types, F
from database.db import get_user, can_request, add_request, get_mode, is_premium
from ai import solve_problem

router = Router()

@router.message(F.text)
async def solve_message(message: types.Message):
    if not message.text or message.text.startswith("/"):
        return
    
    # Проверяем состояние пользователя
    try:
        from handlers.admin_handler import user_pages
        user_state = user_pages.get(message.from_user.id, {})
        if user_state.get("state") in ["waiting_broadcast", "confirm_broadcast"]:
            return
    except:
        pass
    
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("👋 Напишите /start для регистрации")
        return
    
    ok, remaining = can_request(message.from_user.id)
    if not ok:
        await message.answer(
            f"🔒 Лимит исчерпан!\n\n"
            f"Бесплатно: 10 задач/день\n"
            f"Осталось: 0\n\n"
            f"💎 Купите Premium: /subscribe"
        )
        return
    
    premium = is_premium(message.from_user.id)
    status_msg = await message.answer("🔄 Думаю над ответом...")
    
    mode = get_mode(message.from_user.id)
    answer = solve_problem(message.text, mode, premium)
    add_request(message.from_user.id)
    
    emoji = "💬" if mode == "chat" else "📚"
    remaining_after = remaining - 1 if not premium else "∞"
    
    result_text = f"{emoji} {answer}\n\n"
    if not premium:
        result_text += f"🎯 Осталось задач: {remaining_after}"
    else:
        result_text += f"💎 Premium — безлимит"
    
    await status_msg.edit_text(result_text)
