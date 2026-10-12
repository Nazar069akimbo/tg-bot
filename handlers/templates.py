from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from . import helpers
from .image import generate_image

router = Router()


TEMPLATES = {
    "avatar": {
        "title": "🎨 Аватарка для соцсетей",
        "prompts": [
            "Стильная аватарка с неоновой подсветкой, минимализм",
            "Аватарка с космическим фоном и звёздами, футуризм",
            "Аватарка в стиле аниме, яркая, эмоциональная",
            "Аватарка с абстрактными геометрическими формами",
        ]
    },
    "product": {
        "title": "🛒 Карточка для маркетплейса",
        "prompts": [
            "Товар на белом фоне, студийный свет, профессиональное фото",
            "Товар в интерьере, мягкий свет, lifestyle-фото",
            "Товар крупным планом, детализация, коммерческая фотография",
            "Товар с минималистичными декорациями, трендовый стиль",
        ]
    },
    "sticker": {
        "title": "🎭 Стикер с эмоцией",
        "prompts": [
            "Милый стикер с улыбкой, плоский дизайн, белый фон",
            "Стикер с удивлением, яркие цвета, cartoon-стиль",
            "Стикер с грустью, пастельные тона, минимализм",
            "Стикер с восторгом, звёздочки, pop-art",
        ]
    },
    "photo": {
        "title": "📸 Портрет в стиле",
        "prompts": [
            "Портрет в стиле киберпанк, неоновые огни",
            "Портрет в стиле ренессанс, классическая живопись",
            "Портрет в стиле аниме, яркие цвета",
            "Портрет в стиле чёрно-белой фотографии, драматургия",
        ]
    },
    "art": {
        "title": "🖼 Художественная картинка",
        "prompts": [
            "Пейзаж в стиле импрессионизм, масляные краски",
            "Абстрактная композиция, яркие цвета, динамика",
            "Космический пейзаж с планетами и звёздами",
            "Фэнтези-сцена с драконами и замками",
        ]
    },
    "logo": {
        "title": "💼 Логотип",
        "prompts": [
            "Минималистичный логотип, геометрические формы",
            "Логотип с буквой, современный стиль",
            "Абстрактный логотип с градиентами",
            "Логотип в стиле hand-drawn, тёплые тона",
        ]
    },
}


def templates_menu_kb():
    rows = []
    for key, data in TEMPLATES.items():
        rows.append([InlineKeyboardButton(
            text=data["title"],
            callback_data=f"tpl|{key}"
        )])
    rows.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def template_prompts_kb(key: str):
    data = TEMPLATES.get(key)
    if not data:
        return None
    rows = []
    for i, prompt in enumerate(data["prompts"]):
        short = prompt[:40] + ("…" if len(prompt) > 40 else "")
        rows.append([InlineKeyboardButton(
            text=short,
            callback_data=f"tplp|{key}|{i}"
        )])
    rows.append([InlineKeyboardButton(text="🔙 К шаблонам", callback_data="templates")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "templates")
async def templates_cb(callback: types.CallbackQuery):
    text = (
        "🎨 <b>Шаблоны промптов</b>\n\n"
        "Не знаешь, что нарисовать? Выбери готовую идею — бот сам всё сделает."
    )
    try:
        await callback.message.edit_text(text, reply_markup=templates_menu_kb())
    except Exception:
        await callback.message.answer(text, reply_markup=templates_menu_kb())
    await helpers.safe_answer(callback)


@router.callback_query(F.data.startswith("tpl|"))
async def template_cb(callback: types.CallbackQuery):
    key = callback.data.split("|", 1)[1]
    data = TEMPLATES.get(key)
    if not data:
        await helpers.safe_answer(callback, "❌ Шаблон не найден", show_alert=True)
        return

    text = (
        f"{data['title']}\n\n"
        "Выбери один из вариантов — бот сразу сгенерирует картинку.\n"
        "Или напиши свой промпт сообщением."
    )
    kb = template_prompts_kb(key)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await helpers.safe_answer(callback)


@router.callback_query(F.data.startswith("tplp|"))
async def template_prompt_cb(callback: types.CallbackQuery):
    parts = callback.data.split("|")
    if len(parts) < 3:
        return
    key = parts[1]
    try:
        idx = int(parts[2])
    except ValueError:
        return

    data = TEMPLATES.get(key)
    if not data or idx >= len(data["prompts"]):
        await helpers.safe_answer(callback, "❌ Ошибка", show_alert=True)
        return

    prompt = data["prompts"][idx]
    await helpers.safe_answer(callback, "🎨 Генерирую…")

    # Удаляем меню и генерим
    try:
        await callback.message.delete()
    except Exception:
        pass

    await generate_image(callback.message, prompt, callback.from_user.id)
