from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import cursor

router = Router()

@router.message(Command("referral"))
async def referral_cmd(message: types.Message):
    user_id = message.from_user.id
    link = f"https://t.me/ReshebnikPro_bot?start={user_id}"
    
    await message.answer(
        f"👥 **Рефералы**\n\n"
        f"🔗 `{link}`\n\n"
        f"За каждого друга +5 задач!"
    )

@router.callback_query(F.data == "referral")
async def referral_callback(callback: types.CallbackQuery):
    try:
        user_id = callback.from_user.id
        link = f"https://t.me/ReshebnikPro_bot?start={user_id}"
        
        await callback.message.edit_text(
            f"👥 **Рефералы**\n\n"
            f"🔗 `{link}`\n\n"
            f"За каждого друга +5 задач!"
        )
        await callback.answer()
    except Exception as e:
        await callback.answer()
