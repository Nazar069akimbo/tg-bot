from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import *
from . import helpers

router = Router()


async def balance_cmd(message: types.Message, user_id: int = None):
    if user_id is None:
        user_id = message.from_user.id

    tokens = get_tokens(user_id)
    user = get_user(user_id)
    plan = dict(user).get("plan", "basic") if user else "basic"
    plan_name = {"basic": "Базовый", "premium": "Premium", "premium_plus": "Premium+"}.get(plan, plan)

    if tokens > 0:
        text = (
            f"💰 <b>Баланс</b>\n\n"
            f"🪙 Токенов: <b>{tokens}</b>\n"
            f"💳 Тариф: {plan_name}\n\n"
            f"💡 Траты списываются с баланса"
        )
    else:
        text = (
            f"💰 <b>Баланс</b>\n\n"
            f"🪙 Токенов: <b>0</b>\n"
            f"💳 Тариф: {plan_name}\n\n"
            f"💎 Купи токены, чтобы пользоваться ботом: /credits"
        )

    await message.answer(text, reply_markup=helpers.main_menu())


@router.message(Command("balance"))
async def balance_command(message: types.Message):
    await balance_cmd(message)


@router.callback_query(F.data == "balance")
async def balance_cb(callback: types.CallbackQuery):
    await balance_cmd(callback.message, callback.from_user.id)
    await helpers.safe_answer(callback)
