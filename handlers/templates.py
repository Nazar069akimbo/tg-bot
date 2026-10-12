from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from . import helpers
from .image import generate_image

router = Router()


TEMPLATES = {
    "avatar": {
        "title": "🎨 Аватарка для соцсетей",
        "desc": "Стильная аватарка под твой характер или ник. Подходит для Telegram, VK, Instagram.",
        "prompts": [
            "Стильная аватарка с неоновой подсветкой, минимализм, темный фон",
            "Аватарка с космическим фоном и звёздами, футуризм, синие тона",
            "Аватарка в стиле аниме, яркая, эмоциональная, крупный план",
            "Аватарка с абстрактными геометрическими формами, контраст",
        ]
    },
    "product": {
        "title": "🛒 Карточка для маркетплейса",
        "desc": "Профессиональное фото товара для WB, Ozon, Авито. Можно загрузить своё фото — бот улучшит его.",
        "prompts": [
            "Товар на белом фоне, студийный свет, профессиональное фото, high quality",
            "Товар в интерьере, мягкий свет, lifestyle-фото, реалистично",
            "Товар крупным планом, детализация, коммерческая фотография",
            "Товар с минималистичными декорациями, трендовый стиль",
        ]
    },
    "sticker": {
        "title": "🎭 Стикер с эмоцией",
        "desc": "Яркий стикер для Telegram. Можно загрузить фото и превратить в стикер.",
        "prompts": [
            "Милый стикер с улыбкой, плоский дизайн, белый фон",
            "Стикер с удивлением, яркие цвета, cartoon-стиль",
            "Стикер с грустью, пастельные тона, минимализм",
            "Стикер с восторгом, звёздочки, pop-art, яркий",
        ]
    },
    "photo": {
        "title": "📸 Портрет в стиле",
        "desc": "Преврати своё фото в арт. Загрузи фото — бот сделает портрет в выбранном стиле.",
        "prompts": [
            "Портрет в стиле киберпанк, неоновые огни, детализированный",
            "Портрет в стиле ренессанс, классическая живопись, масло",
            "Портрет в стиле аниме, яркие цвета, эмоциональный",
            "Портрет чёрно-белый, драматургия, кинематографичный свет",
        ]
    },
    "art": {
        "title": "🖼 Художественная картинка",
        "desc": "Атмосферные арты для обоев, постов или вдохновения.",
        "prompts": [
            "Пейзаж в стиле импрессионизм, масляные краски, тёплые тона",
            "Абстрактная композиция, яркие цвета, динамика",
            "Космический пейзаж с планетами и звёздами, эпично",
            "Фэнтези-сцена с драконами и замками, детализированно",
        ]
    },
    "logo": {
        "title": "💼 Логотип",
        "desc": "Минималистичный логотип для бренда или проекта. Можно доработать свой.",
        "prompts": [
            "Минималистичный логотип, геометрические формы, чистый дизайн",
            "Логотип с буквой, современный стиль, монохром",
            "Абстрактный логотип с градиентами, тренд",
            "Логотип в стиле hand-drawn, тёплые тона, уникальный",
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
        # Полное описание в кнопке (до 60 символов — лимит Telegram)
        preview = prompt[:60]
        rows.append([InlineKeyboardButton(
            text=f"• {preview}",
            callback_data=f"tplp|{key}|{i}"
        )])
    rows.append([InlineKeyboardButton(text="📷 Загрузить своё фото", callback_data=f"tplphoto|{key}")])
    rows.append([InlineKeyboardButton(text="🔙 К шаблонам", callback_data="templates")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "templates")
async def templates_cb(callback: types.CallbackQuery):
    text = (
        "🎨 <b>Шаблоны промптов</b>\n\n"
        "Не знаешь, что нарисовать? Выбери готовую идею — бот сам всё сделает.\n\n"
        "📷 <b>Или загрузи своё фото</b> — бот превратит его в арт, стикер или улучшит товар."
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
        f"<b>{data['title']}</b>\n\n"
        f"{data['desc']}\n\n"
        "👇 Выбери вариант — бот сразу сгенерирует картинку.\n"
        "📷 Или загрузи своё фото — бот использует его как основу."
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

    try:
        await callback.message.delete()
    except Exception:
        pass

    await generate_image(callback.message, prompt, callback.from_user.id)


@router.callback_query(F.data.startswith("tplphoto|"))
async def template_photo_cb(callback: types.CallbackQuery):
    """Юзер хочет загрузить фото для шаблона."""
    key = callback.data.split("|", 1)[1]
    data = TEMPLATES.get(key)
    if not data:
        await helpers.safe_answer(callback, "❌ Шаблон не найден", show_alert=True)
        return

    helpers.user_pages[callback.from_user.id] = {
        "state": "waiting_template_photo",
        "template_key": key,
    }

    text = (
        f"📷 <b>Загрузка фото для шаблона</b>\n\n"
        f"<b>{data['title']}</b>\n"
        f"{data['desc']}\n\n"
        "Отправь фото (как фото, не файлом). Бот превратит его.\n\n"
        "⏹ /cancel — отмена"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Отмена", callback_data=f"tpl|{key}")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await helpers.safe_answer(callback)
