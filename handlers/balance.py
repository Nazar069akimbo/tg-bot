from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import *
from . import helpers

router = Router()

@router.message(Command("balance"))
async def balance_cmd(message: types.Message):
    user_id = message.from_user.id
    tokens = get_tokens(user_id)
    used, max_req = get_text_requests(user_id)
    await message.answer(
        f"💰 **Баланс**\n\n"
        f"🪙 Токенов: {tokens}\n"
        f"🖼️ Хватит на: {tokens // 10} картинок\n"
        f"📝 Текст: {used}/{max_req} запросов сегодня",
        reply_markup=helpers.main_menu()
    )

@router.callback_query(F.data == "balance")
async def balance_cb(callback: types.CallbackQuery):
    await balance_cmd(callback.message)
    await helpers.safe_answer(callback)
