from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from .. import helpers
from .menu import back_btn, safe_edit
router = Router()

@router.callback_query(F.data == "a_support_tickets")
async def a_support_tickets(callback: types.CallbackQuery):
    await safe_edit(callback, "📩 Тикеты", InlineKeyboardMarkup(inline_keyboard=[[back_btn()]]))
    await helpers.safe_answer(callback)
