from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from database.db import *
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import logging

logger = logging.getLogger(__name__)

user_pages = {}
user_model = {}

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✨ Купить токены", callback_data="buy_tokens"),
         InlineKeyboardButton(text="📊 Баланс", callback_data="balance")],
        [InlineKeyboardButton(text="🎁 Промокод", callback_data="promo_use"),
         InlineKeyboardButton(text="👥 Рефералы", callback_data="referral")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="❓ Помощь", callback_data="help")],
        [InlineKeyboardButton(text="🛡️ Админ", callback_data="admin_panel")]
    ])

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="a_stats"), InlineKeyboardButton(text="📈 Модели", callback_data="a_model_stats")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="a_users"), InlineKeyboardButton(text="⭐ Раздать токены", callback_data="a_give_tokens")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="a_broadcast"), InlineKeyboardButton(text="🚫 Блокировка", callback_data="a_block")],
        [InlineKeyboardButton(text="💾 Бэкап", callback_data="a_backup"), InlineKeyboardButton(text="📩 Обращения", callback_data="a_messages")],
        [InlineKeyboardButton(text="📤 Выгрузить БД", callback_data="a_export_db"), InlineKeyboardButton(text="📥 Восстановить из GitHub", callback_data="a_restore_github")],
        [InlineKeyboardButton(text="💰 Цены", callback_data="a_edit_prices"), InlineKeyboardButton(text="🎫 Промокоды", callback_data="a_promocodes")],
        [InlineKeyboardButton(text="⭐ Баланс Stars", callback_data="a_stars_balance")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

def image_action_buttons(image_id, session_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Поправить", callback_data=f"edit_{image_id}")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
    ])

def edit_in_progress_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏹ Отмена", callback_data="cancel_edit")]
    ])

async def safe_answer(callback: types.CallbackQuery, text: str = None, show_alert: bool = False):
    try:
        if text:
            await callback.answer(text, show_alert=show_alert)
        else:
            await callback.answer()
    except TelegramBadRequest:
        pass
    except Exception:
        pass

def get_user_name(user_id):
    memory = get_user_memory(user_id)
    if memory and memory.get('name'):
        return memory['name']
    return None

def add_watermark(image_data):
    try:
        img = Image.open(BytesIO(image_data))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
        except:
            font = ImageFont.load_default()
        draw.text((10, 10), "Vertex AI", font=font, fill=(255, 255, 255, 128))
        output = BytesIO()
        img.save(output, format='PNG')
        output.seek(0)
        return output.getvalue()
    except:
        return image_data

IMAGE_MODELS = {
    "flux": {"name": "🖼️ Flux Schnell", "price": 10, "api_model": "flux-schnell", "type": "replicate", "description": "⚡ Быстрая, базовая"},
    "flux_2_max": {"name": "🔥 Flux-2-Max", "price": 100, "api_model": "flux-2-max", "type": "replicate", "description": "⭐ ТОПОВОЕ КАЧЕСТВО"}
}
model_stats = {"flux": 0, "flux_2_max": 0}

def get_model_key(user_id):
    return user_model.get(user_id, "flux")

def get_model_config(user_id):
    key = get_model_key(user_id)
    return IMAGE_MODELS.get(key, IMAGE_MODELS["flux"])
