from aiogram import Router, types, F
from database.db import get_user, can_request, add_request, get_mode, is_premium
from ai import solve_problem
from keyboards import main_menu

router = Router()

@router.message(F.text)
async def solve_message(message: types.Message):
    if not message.text or message.text.startswith("/"):
        return
    
    user = get_user(message.from_user.id)
    if not user:
        await message.answer(
            "👋 Напишите /start для регистрации",
            reply_markup=main_menu()
        )
        return
    
    ok, remaining = can_request(message.from_user.id)
    if not ok:
        await message.answer(
            f"🔒 Лимит исчерпан!\n\n"
            f"Бесплатно: 10 запросов/день\n"
            f"Осталось: 0\n\n"
            f"💎 Купите Premium: /subscribe"
        )
        return
    
    premium = is_premium(message.from_user.id)
    status_msg = await message.answer("🤔 Думаю...")
    
    answer = solve_problem(message.text, "chat", premium)
    add_request(message.from_user.id)
    
    remaining_after = remaining - 1 if not premium else "∞"
    
    result_text = f"🧠 {answer}\n\n"
    if not premium:
        result_text += f"🎯 Осталось запросов: {remaining_after}"
    else:
        result_text += f"💎 Premium — безлимит"
    
    await status_msg.edit_text(result_text)
