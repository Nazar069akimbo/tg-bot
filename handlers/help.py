from aiogram import Router, types, F
from aiogram.filters import Command
from . import helpers

router = Router()

HELP_TEXT = (
    "❓ **Помощь**\n\n"
    "✨ Я — **Vertex AI**, твой умный ассистент.\n\n"
    "**Что я умею:**\n"
    "🖼️ Создавать картинки — просто напиши, что нарисовать\n"
    "✏️ Редактировать картинки — нажми «Поправить» под картинкой\n"
    "📄 Анализировать файлы — отправь PDF, DOCX, TXT или CSV\n"
    "🎤 Распознавать голосовые — отправь голосовое сообщение\n"
    "🔍 Искать в интернете — команда /search запрос\n"
    "⏰ Напоминать — команда /remind 10:00 текст\n"
    "🧠 Отвечать на вопросы — просто напиши\n\n"
    "**Команды:**\n"
    "/start — главное меню\n"
    "/profile — профиль\n"
    "/balance — баланс\n"
    "/search — поиск\n"
    "/remind — напоминание\n"
    "/reminders — список напоминаний\n\n"
    "**Тарифы и цены:**\n"
    "💰 Токены продаются в меню «Купить токены»\n"
    "👑 Подписки: Премиум 150⭐/мес, Премиум+ 300⭐/мес\n"
    "🎁 Новым пользователям — 20 токенов бесплатно!\n\n"
    "💡 10 токенов = 1 картинка\n\n"
    "👥 Приглашай друзей по своей реферальной ссылке — получишь +20 токенов за каждого!"
)


async def show_help(message: types.Message):
    await message.answer(HELP_TEXT, reply_markup=helpers.main_menu())


@router.message(Command("help"))
async def help_command(message: types.Message):
    await show_help(message)


@router.callback_query(F.data == "help")
async def help_cb(callback: types.CallbackQuery):
    # ВАЖНО: id пользователя для безопасного показа — из callback.from_user
    text = HELP_TEXT
    try:
        await callback.message.edit_text(text, reply_markup=helpers.main_menu())
    except Exception:
        await callback.message.answer(text, reply_markup=helpers.main_menu())
    await helpers.safe_answer(callback)