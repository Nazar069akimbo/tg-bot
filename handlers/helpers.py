from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from database.db import *
from datetime import datetime, timedelta
import re
import logging

logger = logging.getLogger(__name__)

ADMIN_EMAIL = "mychannell@gmail.com"

user_pages = {}
user_model = {}


def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✨ Купить токены", callback_data="buy_tokens"),
         InlineKeyboardButton(text="📊 Баланс", callback_data="balance")],
        [InlineKeyboardButton(text="💰 Цены", callback_data="prices"),
         InlineKeyboardButton(text="👥 Рефералы", callback_data="referral")],
        [InlineKeyboardButton(text="⏰ Мои напоминания", callback_data="my_reminders")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="❓ Помощь", callback_data="help")],
        [InlineKeyboardButton(text="🛡️ Админ", callback_data="admin_panel")]
    ])


def profile_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑️ Забыть всё", callback_data="forget_all")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
    ])


def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="a_stats"),
         InlineKeyboardButton(text="📈 Модели", callback_data="a_model_stats")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="a_users"),
         InlineKeyboardButton(text="⭐ Раздать токены", callback_data="a_give_tokens")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="a_broadcast"),
         InlineKeyboardButton(text="🚫 Блокировка", callback_data="a_block")],
        [InlineKeyboardButton(text="💾 Бэкап", callback_data="a_backup"),
         InlineKeyboardButton(text="📩 Обращения", callback_data="a_messages")],
        [InlineKeyboardButton(text="📤 Выгрузить БД", callback_data="a_export_db"),
         InlineKeyboardButton(text="📥 Восстановить", callback_data="a_restore_github")],
        [InlineKeyboardButton(text="💰 Цены", callback_data="a_edit_prices"),
         InlineKeyboardButton(text="🎫 Промокоды", callback_data="a_promocodes")],
        [InlineKeyboardButton(text="🎫 Тарифы", callback_data="a_tariffs")],
        [InlineKeyboardButton(text="📊 Статус БД", callback_data="a_db_status")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
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


IMAGE_MODELS = {
    "flux": {"name": "🖼️ Flux Schnell", "price": 10, "api_model": "flux-schnell", "type": "replicate", "description": "⚡ Быстрая"},
    "flux_2_max": {"name": "🔥 Flux-2-Max", "price": 100, "api_model": "flux-2-max", "type": "replicate", "description": "⭐ ТОП"}
}
model_stats = {"flux": 0, "flux_2_max": 0}

AVAILABLE_MODELS = {
    "image_generate": [
        ("flux-schnell", "🖼️ Flux Schnell"),
        ("flux-2-max", "🔥 Flux-2-Max"),
    ],
    "prompt_enhance": [
        ("gpt-4.1-nano", "🧠 GPT-4.1 nano"),
        ("deepseek-v4-flash", "🧠 DeepSeek Flash"),
    ],
    "text_chat": [
        ("deepseek-v4-flash", "💬 DeepSeek Flash"),
        ("gpt-4.1-nano", "💬 GPT-4.1 nano"),
    ],
}

TASK_NAMES = {
    "image_generate": "🎨 Генерация картинок",
    "prompt_enhance": "🧠 Улучшение промпта",
    "text_chat": "💬 Текстовый чат",
}


def get_model_key(user_id):
    return user_model.get(user_id, "flux")


def get_model_config(user_id):
    key = get_model_key(user_id)
    return IMAGE_MODELS.get(key, IMAGE_MODELS["flux"])


def build_reminder_time(date_str, time_str):
    """Единая функция для парсинга даты/времени напоминания."""
    now = datetime.now()
    today = now.date()

    if not time_str:
        return None

    time_str = str(time_str).strip().lower()
    date_str = str(date_str or "").strip().lower()

    # "через N минут/часов/дней"
    m = re.match(r'через\s+(\d+)\s*(мин|минут|час|часов|дн|дней|день)', time_str)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        if unit.startswith('мин'):
            return now + timedelta(minutes=amount)
        if unit.startswith('час'):
            return now + timedelta(hours=amount)
        if unit.startswith('дн'):
            return now + timedelta(days=amount)

    m = re.match(r'через\s+(\d+)$', time_str)
    if m:
        return now + timedelta(minutes=int(m.group(1)))

    # "12.00", "12:00", "12,00"
    time_str = time_str.replace(".", ":").replace(",", ":")
    m = re.match(r'^(\d{1,2}):(\d{2})$', time_str)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        time_obj = datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time()

        if date_str in (None, "", "today", "сегодня"):
            full = datetime.combine(today, time_obj)
            if full < now:
                full += timedelta(days=1)
            return full
        elif date_str in ("tomorrow", "завтра"):
            return datetime.combine(today + timedelta(days=1), time_obj)
        else:
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d").date()
                if d < today:
                    full = datetime.combine(today, time_obj)
                    if full < now:
                        full += timedelta(days=1)
                    return full
                return datetime.combine(d, time_obj)
            except ValueError:
                return None

    return None
