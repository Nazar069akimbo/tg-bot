from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from . import helpers
import logging

router = Router()
logger = logging.getLogger(__name__)

ADMIN_ID = int(__import__('os').getenv('ADMIN_ID', 6957852385))


def support_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
    ])


@router.callback_query(F.data == "support")
async def support_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    ticket = get_user_ticket(user_id)

    if ticket:
        msgs = get_ticket_messages(ticket['id'])
        text = f"💬 **Диалог с поддержкой** (тикет #{ticket['id']})\n\n"
        for m in msgs[-20:]:
            who = "👤 Ты" if m['sender'] == 'user' else "🛡 Админ"
            text += f"{who}: {m['text']}\n"
        text += "\n✍️ Просто напиши следующее сообщение."
        await callback.message.edit_text(text, reply_markup=support_kb())
    else:
        helpers.user_pages[user_id] = {"state": "waiting_support_message"}
        await callback.message.edit_text(
            "💬 **Поддержка**\n\n"
            "Напиши свой вопрос — админ ответит в этом же чате.\n\n"
            "⏹ /cancel — отмена",
            reply_markup=support_kb()
        )
    await helpers.safe_answer(callback)


async def handle_support_message(message: types.Message):
    """Обрабатывает сообщение пользователя в поддержку."""
    user_id = message.from_user.id
    text = message.text.strip()

    if text == "/cancel":
        helpers.user_pages.pop(user_id, None)
        await message.answer("✅ Отменено", reply_markup=helpers.main_menu())
        return

    ticket = get_user_ticket(user_id)

    if not ticket:
        ticket_id = create_support_ticket(user_id, message.from_user.username or "", text)
        await message.answer(
            f"✅ Сообщение отправлено (тикет #{ticket_id}).\n\n"
            f"Админ ответит в этом чате.",
            reply_markup=helpers.main_menu()
        )
        notif_text = f"📩 Новое обращение от {message.from_user.full_name} (@{message.from_user.username or '—'}, ID {user_id})\n\n{text}"
    else:
        add_support_message(ticket['id'], 'user', text)
        await message.answer("✅ Отправлено админу.", reply_markup=helpers.main_menu())
        notif_text = f"💬 Ответ в тикете #{ticket['id']} от {message.from_user.full_name} (ID {user_id})\n\n{text}"

    helpers.user_pages.pop(user_id, None)

    # Уведомление админу
    try:
        await message.bot.send_message(ADMIN_ID, notif_text)
    except Exception as e:
        logger.warning(f"⚠️ Не отправил админу: {e}")
        add_admin_notification(notif_text, user_id)


@router.message(Command("support"))
async def support_cmd(message: types.Message):
    helpers.user_pages[message.from_user.id] = {"state": "waiting_support_message"}
    await message.answer(
        "💬 **Поддержка**\n\n"
        "Напиши свой вопрос — админ ответит в этом же чате.\n\n"
        "⏹ /cancel — отмена",
        reply_markup=support_kb()
    )
