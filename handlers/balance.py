from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import *
from . import helpers

router = Router()


async def balance_cmd(message: types.Message, user_id: int = None):
    if user_id is None:
        user_id = message.from_user.id
    tokens = get_tokens(user_id)
    text_avail, text_limit = get_text_tokens_today(user_id)
    img_used, img_limit = get_week_images_used(user_id)

    await message.answer(
        f"💰 **Баланс**\n\n"
        f"🪙 Токенов: {tokens}\n"
        f"📝 Текст: {text_avail}/{text_limit} сегодня\n"
        f"🎨 Картинок: {img_used}/{img_limit} на этой неделе",
        reply_markup=helpers.main_menu()
    )


@router.message(Command("balance"))
async def balance_command(message: types.Message):
    await balance_cmd(message)


@router.callback_query(F.data == "balance")
async def balance_cb(callback: types.CallbackQuery):
    await balance_cmd(callback.message, callback.from_user.id)
    await helpers.safe_answer(callback)
