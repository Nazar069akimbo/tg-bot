from aiogram import Router, types, F
from aiogram.filters import Command
from . import helpers

router = Router()
ADMIN_EMAIL = "mychannell@gmail.com"

HELP_TEXT = (
    "❓ Помощь\n\n"
    "✨ Я — Vertex AI, твой ассистент.\n\n"
    "Что умею:\n"
    "🖼️ Создавать картинки\n"
    "🎨 Делать стикеры\n"
    "📄 Анализировать файлы (PDF, DOCX, TXT, CSV)\n"
    "🎤 Распознавать голосовые\n"
    "🔍 Искать в интернете\n"
    "⏰ Напоминать\n"
    "🧠 Запоминать факты\n"
    "💬 Отвечать на вопросы\n\n"
    "Команды:\n"
    "/start — меню\n"
    "/profile — профиль\n"
    "/balance — баланс\n"
    "/prices — цены\n"
    "/credits — купить токены\n"
    "/settings — настройки моделей\n"
    "/reminders — напоминания\n\n"
    "Тарифы:\n"
    "💰 10 токенов = 1 картинка (Flux Schnell)\n"
    "📊 20 запросов в день бесплатно\n"
    "🎁 Новичкам — 20 токенов!\n\n"
    f"📧 Проблемы? Пиши: {ADMIN_EMAIL}"
)


async def show_help(message: types.Message):
    await message.answer(HELP_TEXT, reply_markup=helpers.main_menu())


@router.message(Command("help"))
async def help_command(message: types.Message):
    await show_help(message)


@router.callback_query(F.data == "help")
async def help_cb(callback: types.CallbackQuery):
    try:
        await callback.message.edit_text(HELP_TEXT, reply_markup=helpers.main_menu())
    except Exception:
        await callback.message.answer(HELP_TEXT, reply_markup=helpers.main_menu())
    await helpers.safe_answer(callback)


@router.message(Command("settings"))
async def settings_cmd(message: types.Message):
    user_id = message.from_user.id
    ask_text = get_setting(f"ask_model_{user_id}") != "no"
    ask_image = get_setting(f"ask_image_model_{user_id}") != "no"

    text = (
        "⚙️ Настройки\n\n"
        f"Выбор модели текста: {'✅ спрашиваю' if ask_text else '❌ не спрашиваю'}\n"
        f"Выбор модели картинок: {'✅ спрашиваю' if ask_image else '❌ не спрашиваю'}\n\n"
        "Нажми, чтобы изменить:"
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"Текст: {'✅' if ask_text else '❌'}",
            callback_data="toggle_ask_text"
        )],
        [InlineKeyboardButton(
            text=f"Картинки: {'✅' if ask_image else '❌'}",
            callback_data="toggle_ask_image"
        )],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
    ])
    await message.answer(text, reply_markup=kb)
