from aiogram import Router, types, F
from database.db import *
from ai.client import solve_problem, analyze_intent, search_web, generate_ack
from . import helpers
from .image import generate_image
from utils.user_storage import set_user_name, add_fact
import logging

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.text)
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()

    if not text or text.startswith("/"):
        return

    state = helpers.user_pages.get(user_id, {})

    if state.get("state") == "waiting_reminder_clarification":
        from .reminders import handle_clarification
        await handle_clarification(message, text)
        return

    if state.get("state") in ["waiting_broadcast", "waiting_block_user", "waiting_contact",
                              "waiting_give_tokens", "waiting_price", "waiting_promo_code",
                              "waiting_tariff_edit", "waiting_tariff_add"]:
        from .admin import handle_admin_input
        await handle_admin_input(message)
        return

    if state.get("state") == "waiting_promo_use":
        success, msg = use_promocode(text.upper(), user_id)
        await message.answer(msg, reply_markup=helpers.main_menu())
        helpers.user_pages.pop(user_id, None)
        return

    if state.get("state") == "waiting_name":
        set_user_name(user_id, text)
        helpers.user_pages.pop(user_id, None)
        await message.answer(f"Ок, {text}! Приятно познакомиться 😊")
        from .start import start_cmd
        await start_cmd(message)
        return

    reminder_state = state if state.get("state") == "waiting_reminder_clarification" else None
    action, params = analyze_intent(user_id, text, reminder_state=reminder_state)

    if action == 'generate_image':
        await generate_image(message, params.get('prompt', text))

    elif action == 'set_reminder':
        from .reminders import create_reminder_from_ai
        await create_reminder_from_ai(message, params)

    elif action == 'list_reminders':
        from .reminders import list_reminders_msg
        await list_reminders_msg(message)

    elif action == 'delete_reminder':
        target = params.get("text", "")
        if target:
            delete_reminder_by_text(user_id, target)
            await message.answer(f"✅ Удалено: {target}")
        else:
            await message.answer("❌ Не понял, какое напоминание удалить")

    elif action == 'delete_all_reminders':
        delete_all_reminders(user_id)
        await message.answer("🗑️ Все напоминания удалены")

    elif action == 'search_web':
        status = await message.answer("🔍 Ищу...")
        answer = search_web(params.get('query', text))
        await status.edit_text(f"🔍 Результат:\n\n{answer}")

    elif action == 'remember':
        fact = params.get("fact", "").strip()
        if fact:
            add_fact(user_id, fact)
            ack = generate_ack(fact)
            await message.answer(ack)
        else:
            await message.answer("Запомнил 😊")

    elif action == 'show_prices':
        from .payments import prices_text, prices_kb
        await message.answer(prices_text(), reply_markup=prices_kb())

    elif action == 'show_balance':
        await balance_cmd(message)

    elif action == 'show_referral':
        await send_referral_info(message)

    elif action == 'show_profile':
        from .profile import show_profile
        await show_profile(message)

    elif action == 'show_help':
        from .help import show_help
        await show_help(message)

    else:
        await generate_text(message)


async def generate_text(message: types.Message):
    user_id = message.from_user.id
    if not can_request_text(user_id):
        await message.answer("🔒 Лимит запросов исчерпан!")
        return

    status_msg = await message.answer("🤔 Думаю...")
    try:
        answer = solve_problem(message.text, "chat", False, user_id=user_id)
        add_text_request(user_id)
        used, max_req = get_text_requests(user_id)
        add_to_context(user_id, message.text)
        await status_msg.edit_text(f"🧠 {answer}\n\n📝 Осталось: {max_req - used}/{max_req}")
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")


async def balance_cmd(message: types.Message):
    user_id = message.from_user.id
    tokens = get_tokens(user_id)
    used, max_req = get_text_requests(user_id)
    await message.answer(
        f"💰 Баланс\n\n🪙 Токенов: {tokens}\n🖼️ Картинок: {tokens // 10}\n📝 Текст: {used}/{max_req}",
        reply_markup=helpers.main_menu()
    )


async def send_referral_info(message: types.Message):
    user_id = message.from_user.id
    count = get_referral_count(user_id)
    link = f"https://t.me/Vertex1bot?start={user_id}"
    await message.answer(
        f"👥 Рефералы\n\n👤 Приглашено: {count}\n🎁 +20 токенов за друга\n\n🔗 {link}",
        reply_markup=helpers.main_menu()
    )
