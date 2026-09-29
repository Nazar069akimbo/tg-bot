from aiogram import Router, types, F
from aiogram.filters import Command
from . import helpers

router = Router()

HELP_TEXT = (
    "❓ Помощь\n\n"
    "✨ Я — Vertex AI, твой умный ассистент.\n\n"
    "Что я умею:\n"
    "🖼️ Создавать картинки — просто напиши, что нарисовать\n"
    "🎨 Делать стикеры — нажми кнопку под картинкой\n"
    "📄 Анализировать файлы — отправь PDF, DOCX, TXT или CSV\n"
    "🎤 Распознавать голосовые — отправь голосовое\n"
    "🔍 Искать в интернете — просто напиши «Найди погоду в Минске»\n"
    "⏰ Напоминать — «Напомни завтра в 10 купить хлеб»\n"
    "🧠 Запоминать — «Меня зовут Паша», «Я люблю футбол»\n"
    "💬 Отвечать на вопросы — просто напиши\n\n"
    "Команды:\n"
    "/start — главное меню\n"
    "/profile — профиль\n"
    "/balance — баланс\n"
    "/prices — цены\n"
    "/credits — купить токены\n"
    "/reminders — список напоминаний\n"
    "/help — эта справка\n\n"
    "Примеры:\n"
    "• «Нарисуй кота в шляпе»\n"
    "• «Напомни завтра в 10 позвонить маме»\n"
    "• «Найди курс доллара»\n"
    "• «Меня зовут Паша»\n\n"
    "Тарифы:\n"
    "💰 10 токенов = 1 картинка\n"
    "🎁 Новичкам — 20 токенов бесплатно!"
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
