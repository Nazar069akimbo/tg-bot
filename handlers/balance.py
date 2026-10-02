from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import *
from . import helpers

router = Router()


async def balance_cmd(message: types.Message, user_id: int = None):
    if user_id is None:
        user_id = message.from_user.id
    tokens = get_tokens(user_id)
    used, limit = get_daily_usage(user_id)
    left = limit - used
    await message.answer(
        f"💰 Баланс\n\n"
        f"🪙 Токенов: {tokens}\n"
        f"📊 Дневной лимит: {used}/{limit} (осталось {left})\n\n"
        f"💡 Токены тратятся на все запросы ИИ.",
        reply_markup=helpers.main_menu()
    )


@router.message(Command("balance"))
async def balance_command(message: types.Message):
    await balance_cmd(message)


@router.callback_query(F.data == "balance")
async def balance_cb(callback: types.CallbackQuery):
    await balance_cmd(callback.message, callback.from_user.id)
    await helpers.safe_answer(callback)
