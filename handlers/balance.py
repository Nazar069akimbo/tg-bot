from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import *
from . import helpers

router = Router()

async def balance_cmd(message: types.Message, user_id: int = None):
    """Показать баланс. user_id можно передать явно (для callback'ов,
    где message.from_user — это бот, и токены покажутся как 0)."""
    if user_id is None:
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

@router.message(Command("balance"))
async def balance_command(message: types.Message):
    await balance_cmd(message)

@router.callback_query(F.data == "balance")
async def balance_cb(callback: types.CallbackQuery):
    # ВАЖНО: берём id пользователя из callback.from_user, а не из message.
    # callback.message.from_user — это бот, поэтому старый код всегда показывал 0.
    await balance_cmd(callback.message, callback.from_user.id)
    await helpers.safe_answer(callback)
