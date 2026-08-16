from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from . import helpers
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "referral")
async def referral_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    count = get_referral_count(user_id)
    link = f"https://t.me/Vertex1bot?start={user_id}"
    text = (
        "👥 **Рефералы**\n\n"
        f"👤 Приглашено: {count}\n"
        f"🎁 Бонус: +20 токенов за друга\n\n"
        f"🔗 Твоя ссылка:\n{link}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться", url=f"https://t.me/share/url?url={link}&text=🤖 Vertex AI!")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
    )
    await helpers.safe_answer(callback)
