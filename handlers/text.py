from aiogram import Router, types, F
from database.db import *
from ai.client import solve_problem
from . import helpers
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.message(F.text)
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Проверяем состояния
    state = helpers.user_pages.get(user_id, {})
    
    if state.get("state") == "waiting_name":
        from .start import start_cmd
        set_user_name(user_id, text)
        helpers.user_pages.pop(user_id, None)
        await message.answer(f"✅ Отлично! Я запомнил тебя.")
        await start_cmd(message)
        return

    if state.get("state") == "waiting_edit":
        await handle_edit(message)
        return

    if state.get("state") == "waiting_promo_use":
        success, msg = use_promocode(text.upper(), user_id)
        await message.answer(msg, reply_markup=helpers.main_menu())
        helpers.user_pages.pop(user_id, None)
        return

    # Обычный текст
    await generate_text(message)

async def generate_text(message: types.Message):
    user_id = message.from_user.id
    if not can_request_text(user_id):
        await message.answer("🔒 Лимит запросов исчерпан! Завтра будет новый день.")
        return

    status_msg = await message.answer("🤔 Думаю...")
    try:
        answer = solve_problem(message.text, "chat", False)
        add_text_request(user_id)
        used, max_req = get_text_requests(user_id)
        add_to_context(user_id, message.text)
        await status_msg.edit_text(f"🧠 {answer}\n\n📝 Осталось: {max_req - used}/{max_req}")
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def handle_edit(message: types.Message):
    user_id = message.from_user.id
    state = helpers.user_pages.get(user_id, {})
    image_id = state.get("image_id")
    if not image_id:
        await message.answer("❌ Нет картинки для правки")
        return

    last_img = get_image_by_id(image_id)
    if not last_img:
        await message.answer("❌ Картинка не найдена")
        return

    full_prompt = last_img.get('prompt', '')
    new_prompt = f"{full_prompt}, {message.text}"
    
    from .image import generate_image
    await generate_image(message, new_prompt)
    helpers.user_pages.pop(user_id, None)
