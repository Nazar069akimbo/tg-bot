from aiogram import Router, types, F
from database.db import *
from . import helpers
import logging

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "promo_use")
async def promo_use_cb(callback: types.CallbackQuery):
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_promo_use"}
    await callback.message.edit_text(
        "🎁 Введи промокод:\n\n"
        "Пример: WELCOME\n\n"
        "⏹ /cancel — отмена",
        reply_markup=helpers.main_menu()
    )
    await helpers.safe_answer(callback)
