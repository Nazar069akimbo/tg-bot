from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.user_storage import load_profile, load_meta, load_history
from . import helpers
import logging

router = Router()
logger = logging.getLogger(__name__)


def memory_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
    ])


async def show_memory(message: types.Message, user_id: int = None):
    if user_id is None:
        user_id = message.from_user.id

    profile = load_profile(user_id)
    meta = load_meta(user_id)
    history = load_history(user_id)
    prefs = profile.get("preferences", {})
    name = profile.get("name") or "—"

    text = (
        f"🧠 **Что я о тебе знаю**\n\n"
        f"🪪 Имя: {name}\n"
        f"🎨 Стиль: {prefs.get('style') or '—'}\n"
        f"🌈 Цвета: {prefs.get('colors') or '—'}\n"
        f"🎯 Хобби: {', '.join(prefs.get('hobbies') or []) or '—'}\n"
        f"💬 Любимые темы: {', '.join(prefs.get('favorite_topics') or []) or '—'}\n\n"
        f"🖼️ Картинок: {meta.get('images_count', 0)}\n"
        f"📝 Сообщений: {len(history)}\n"
    )
    try:
        await message.edit_text(text, reply_markup=memory_kb())
    except Exception:
        await message.answer(text, reply_markup=memory_kb())


@router.message(Command("memory"))
async def memory_cmd(message: types.Message):
    await show_memory(message)


@router.callback_query(F.data == "my_memory")
async def memory_cb(callback: types.CallbackQuery):
    await show_memory(callback.message, callback.from_user.id)
    await helpers.safe_answer(callback)
