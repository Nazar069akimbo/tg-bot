from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from . import helpers
from database.db import get_setting

router = Router()
ADMIN_EMAIL = "mychannell069@gmail.com"

HELP_TEXT = (
    "❓ <b>Помощь</b>\n\n"
    "✨ <b>Что я умею</b>\n"
    "🖼️ Генерировать картинки — «нарисуй кота в шляпе»\n"
    "📝 Отвечать на вопросы — «расскажи про космос»\n"
    "✍️ Писать стихи и тексты — «сочини стих про осень»\n"
    "🎤 Понимать голосовые\n"
    "📄 Анализировать файлы (PDF, DOCX, TXT, CSV)\n"
    "🔍 Искать в интернете — /search\n"
    "⏰ Напоминать — «напомни в 18:00 позвонить»\n"
    "🧠 Запоминать факты — «запомни, я люблю кофе»\n"
    "🎁 Ежедневный бонус — /bonus\n"
    "🏆 Ачивки за действия — в профиле\n"
    "🖼 Галерея картинок — Premium и выше\n"
    "👥 Приглашать друзей — /referral\n\n"
    "⚙️ <b>Команды</b>\n"
    "/start — меню\n"
    "/balance — баланс\n"
    "/profile — профиль\n"
    "/prices — цены\n"
    "/credits — купить токены\n"
    "/bonus — ежедневный бонус\n"
    "/reminders — напоминания\n"
    "/search — поиск в интернете\n"
    "/help — помощь\n"
    "/support — поддержка\n\n"
    "💰 <b>Тарифы</b>\n"
    "• Flux Schnell — 10 токенов (~2.5 ₽)\n"
    "• GPT-4.1 nano — 1 токен (~25 копеек)\n"
    "• Premium — 500 ₽ / 30 дней\n"
    "• Premium+ — 1000 ₽ / 30 дней\n\n"
    "💡 <b>Совет</b>\n"
    "Чем дороже модель — тем лучше качество. Дешёвые модели — для простых задач.\n\n"
    f"📧 Проблемы? Пиши: {ADMIN_EMAIL}"
)


async def show_help(message: types.Message):
    # Удаляем старое сообщение, чтобы новое открылось с начала
    try:
        await message.delete()
    except Exception:
        pass
    await message.answer(HELP_TEXT, reply_markup=helpers.main_menu())


@router.message(Command("help"))
async def help_command(message: types.Message):
    await show_help(message)


@router.callback_query(F.data == "help")
async def help_cb(callback: types.CallbackQuery):
    # Удаляем старое сообщение — новое откроется с начала
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(HELP_TEXT, reply_markup=helpers.main_menu())
    await helpers.safe_answer(callback)


@router.message(Command("settings"))
async def settings_cmd(message: types.Message):
    user_id = message.from_user.id
    ask_text = get_setting(f"ask_model_{user_id}") != "no"
    ask_image = get_setting(f"ask_image_model_{user_id}") != "no"

    text = (
        "⚙️ <b>Настройки</b>\n\n"
        f"Выбор модели текста: {'✅ спрашиваю' if ask_text else '❌ не спрашиваю'}\n"
        f"Выбор модели картинок: {'✅ спрашиваю' if ask_image else '❌ не спрашиваю'}\n\n"
        "Нажми, чтобы изменить:"
    )
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
