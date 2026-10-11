from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from . import helpers
import os, logging

router = Router()
logger = logging.getLogger(__name__)

ADMIN_ID = int(os.getenv('ADMIN_ID', 6957852385))


# ==================== КЛАВИАТУРЫ ====================

def support_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 История", callback_data="support_history")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
    ])


def rating_kb(ticket_id: int):
    """Клавиатура оценки 1–5 звёзд."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐", callback_data=f"rate|{ticket_id}|1"),
            InlineKeyboardButton(text="⭐⭐", callback_data=f"rate|{ticket_id}|2"),
            InlineKeyboardButton(text="⭐⭐⭐", callback_data=f"rate|{ticket_id}|3"),
        ],
        [
            InlineKeyboardButton(text="⭐⭐⭐⭐", callback_data=f"rate|{ticket_id}|4"),
            InlineKeyboardButton(text="⭐⭐⭐⭐⭐", callback_data=f"rate|{ticket_id}|5"),
        ],
    ])


def support_kb_after_close():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Новый вопрос", callback_data="support")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
    ])


# ==================== УТИЛИТЫ ====================

async def replace_message(callback: types.CallbackQuery, text: str, reply_markup=None):
    """Удаляет старое сообщение и отправляет новое на его место."""
    try:
        await callback.message.delete()
    except Exception:
        pass
    try:
        await callback.message.answer(text, reply_markup=reply_markup)
    except Exception as e:
        logger.warning(f"⚠️ replace_message: {e}")


def format_history(msgs: list) -> str:
    """Форматирует историю диалога. ID — кликабельные."""
    lines = []
    for m in msgs:
        sender = m.get("sender")
        if sender == "user":
            who = "👤 <b>Вы</b>"
        else:
            who = "🛡 <b>Поддержка</b>"
        # Экранируем HTML-символы в тексте
        txt = str(m.get("text", ""))
        txt = txt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        lines.append(f"{who}:\n{txt}")
    return "\n\n".join(lines)


# ==================== ВХОД В ПОДДЕРЖКУ ====================

@router.callback_query(F.data == "support")
async def support_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    ticket = get_user_ticket(user_id)

    if ticket:
        msgs = get_ticket_messages(ticket['id'])
        text = f"💬 <b>Диалог с поддержкой</b> (тикет #{ticket['id']})\n\n"
        if msgs:
            text += format_history(msgs[-15:])
        else:
            text += "<i>Пока пусто. Напиши первое сообщение.</i>"
        text += "\n\n✍️ Просто напиши следующее сообщение."

        helpers.user_pages[user_id] = {"state": "waiting_support_message", "ticket_id": ticket['id']}
        await replace_message(callback, text, support_kb())
    else:
        helpers.user_pages[user_id] = {"state": "waiting_support_message"}
        text = (
            "💬 <b>Поддержка</b>\n\n"
            "Напиши свой вопрос — админ ответит прямо в этом чате.\n"
            "Ты сможешь отвечать на его сообщения сколько угодно раз.\n\n"
            "⏹ /cancel — отмена"
        )
        await replace_message(callback, text, support_kb())

    await helpers.safe_answer(callback)


@router.message(Command("support"))
async def support_cmd(message: types.Message):
    user_id = message.from_user.id
    helpers.user_pages[user_id] = {"state": "waiting_support_message"}
    await message.answer(
        "💬 <b>Поддержка</b>\n\n"
        "Напиши свой вопрос — админ ответит прямо в этом чате.\n\n"
        "⏹ /cancel — отмена",
        reply_markup=support_kb()
    )


@router.callback_query(F.data == "support_history")
async def support_history_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    ticket = get_user_ticket(user_id)
    if not ticket:
        await helpers.safe_answer(callback, "Нет открытого тикета", show_alert=True)
        return

    msgs = get_ticket_messages(ticket['id'], limit=50)
    text = f"📜 <b>История тикета #{ticket['id']}</b>\n\n"
    if msgs:
        text += format_history(msgs)
    else:
        text += "<i>Пока нет сообщений</i>"
    if len(text) > 4000:
        text = text[:4000] + "\n\n<i>...и другие (обрезано)</i>"
    await replace_message(callback, text, support_kb())
    await helpers.safe_answer(callback)


# ==================== ОБРАБОТКА СООБЩЕНИЙ ЮЗЕРА ====================

async def handle_support_message(message: types.Message):
    """Юзер пишет в поддержку. Если тикет закрыт — открываем новый."""
    user_id = message.from_user.id
    text = (message.text or "").strip()

    if text == "/cancel":
        helpers.user_pages.pop(user_id, None)
        await message.answer("✅ Отменено", reply_markup=helpers.main_menu())
        return

    if not text:
        await message.answer("❌ Отправь текст")
        return

    # Экранируем HTML
    safe_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    ticket = get_user_ticket(user_id)

    if not ticket:
        # Создаём новый тикет
        ticket_id = create_support_ticket(user_id, message.from_user.username or "", safe_text)
        user_link = helpers.user_link(user_id, message.from_user.full_name or str(user_id))
        notif = (
            f"📩 <b>Новое обращение</b>\n\n"
            f"👤 {user_link}\n"
            f"🔗 @{message.from_user.username or '—'}\n"
            f"🆔 <code>{user_id}</code>\n"
            f"🎫 Тикет #{ticket_id}\n\n"
            f"💬 {safe_text}"
        )
        await message.answer(
            f"✅ Сообщение отправлено (тикет #{ticket_id}).\n\n"
            "Админ ответит в этом чате. Ты сможешь отвечать сколько угодно.",
            reply_markup=helpers.main_menu()
        )
    else:
        # Отвечаем в существующий
        add_support_message(ticket['id'], 'user', safe_text)
        user_link = helpers.user_link(user_id, message.from_user.full_name or str(user_id))
        notif = (
            f"💬 <b>Ответ в тикете #{ticket['id']}</b>\n\n"
            f"👤 {user_link}\n"
            f"🆔 <code>{user_id}</code>\n\n"
            f"💬 {safe_text}"
        )
        await message.answer("✅ Отправлено админу.", reply_markup=helpers.main_menu())

    helpers.user_pages.pop(user_id, None)

    # Уведомляем админа
    try:
        await message.bot.send_message(ADMIN_ID, notif)
    except Exception as e:
        logger.warning(f"⚠️ Не отправил админу: {e}")
        try:
            add_admin_notification(notif, user_id)
        except Exception:
            pass


# ==================== ОЦЕНКА ТИКЕТА ====================

@router.callback_query(F.data.startswith("rate|"))
async def rate_cb(callback: types.CallbackQuery):
    parts = callback.data.split("|")
    if len(parts) < 3:
        await helpers.safe_answer(callback, "❌ Ошибка", show_alert=True)
        return

    try:
        ticket_id = int(parts[1])
        rating = int(parts[2])
    except ValueError:
        await helpers.safe_answer(callback, "❌ Ошибка", show_alert=True)
        return

    user_id = callback.from_user.id

    # Проверяем, что этот тикет принадлежит юзеру
    ticket = get_ticket(ticket_id)
    if not ticket or ticket['user_id'] != user_id:
        await helpers.safe_answer(callback, "❌ Тикет не найден", show_alert=True)
        return

    # Проверяем, не оценивал ли уже
    existing = get_ticket_rating(ticket_id)
    if existing and existing['user_id'] == user_id:
        await helpers.safe_answer(callback, "✅ Ты уже оценил этот тикет", show_alert=True)
        return

    save_ticket_rating(ticket_id, user_id, rating)
    stars = "⭐" * rating
    text = (
        f"🙏 <b>Спасибо за оценку!</b>\n\n"
        f"Ты поставил: {stars} ({rating}/5)\n\n"
        f"Оценка помогает нам стать лучше 💙"
    )
    await replace_message(callback, text, support_kb_after_close())

    # Уведомляем админа
    try:
        user_link = helpers.user_link(user_id, callback.from_user.full_name or str(user_id))
        await callback.bot.send_message(
            ADMIN_ID,
            f"⭐ <b>Оценка тикета #{ticket_id}</b>\n\n"
            f"👤 {user_link}\n"
            f"🆔 <code>{user_id}</code>\n"
            f"Оценка: {stars} ({rating}/5)"
        )
    except Exception as e:
        logger.warning(f"⚠️ Не отправил оценку админу: {e}")

    await helpers.safe_answer(callback, "✅ Спасибо!")


# ==================== ЗАКРЫТИЕ ТИКЕТА (вызов из админки) ====================

async def notify_user_ticket_closed(bot, ticket_id: int, user_id: int):
    """Сообщает юзеру, что тикет закрыт, и просит оценку."""
    text = (
        f"✅ <b>Тикет #{ticket_id} закрыт</b>\n\n"
        "Спасибо за обращение! Если хочешь, поставь оценку нашей поддержке:"
    )
    try:
        await bot.send_message(user_id, text, reply_markup=rating_kb(ticket_id))
    except Exception as e:
        logger.warning(f"⚠️ Не отправил юзеру уведомление о закрытии: {e}")
