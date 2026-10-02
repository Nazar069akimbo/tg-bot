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
        [InlineKeyboardButton(text="⚙️ Сменить модель", callback_data="change_model")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="❓ Помощь", callback_data="help")],
        [InlineKeyboardButton(text="🛡️ Админ", callback_data="admin_panel")]
    ])


def change_model_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧠 Текст", callback_data="change_model_text")],
        [InlineKeyboardButton(text="🎨 Картинки", callback_data="change_model_image")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
    ])


def profile_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑️ Забыть всё", callback_data="forget_all")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
    ])


def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="a_stats"),
         InlineKeyboardButton(text="👥 Пользователи", callback_data="a_users")],
        [InlineKeyboardButton(text="⭐ Раздать токены", callback_data="a_give_tokens"),
         InlineKeyboardButton(text="📢 Рассылка", callback_data="a_broadcast")],
        [InlineKeyboardButton(text="🚫 Блокировка", callback_data="a_block"),
         InlineKeyboardButton(text="💾 Бэкап", callback_data="a_backup")],
        [InlineKeyboardButton(text="📩 Обращения", callback_data="a_messages"),
         InlineKeyboardButton(text="📤 Выгрузить БД", callback_data="a_export_db")],
        [InlineKeyboardButton(text="📥 Восстановить", callback_data="a_restore_github"),
         InlineKeyboardButton(text="🎫 Промокоды", callback_data="a_promocodes")],
        [InlineKeyboardButton(text="🎫 Тарифы", callback_data="a_tariffs"),
         InlineKeyboardButton(text="📊 Статус БД", callback_data="a_db_status")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])


async def safe_answer(callback: types.CallbackQuery, text: str = None, show_alert: bool = False):
    try:
        if text:
            await callback.answer(text, show_alert=show_alert)
        else:
            await callback.answer()
    except Exception:
        pass


def get_user_name(user_id):
    try:
        from utils.user_storage import load_profile
        profile = load_profile(user_id)
        return profile.get("name") if profile else None
    except Exception:
        return None


# ===== МОДЕЛИ =====
AVAILABLE_MODELS = {
    "text_chat": [
        ("gpt-4.1-nano", "⚡ GPT-4.1 nano", 1, "free"),
        ("deepseek-v4-flash", "💰 DeepSeek Flash", 1, "free"),
        ("gemini-2.5-flash-lite", "🌐 Gemini Flash Lite", 2, "premium"),
        ("qwen-3.6-flash", "🟣 Qwen Flash", 2, "premium"),
        ("gpt-4.1-mini", "🧠 GPT-4.1 Mini", 2, "premium"),
        ("claude-haiku", "🎭 Claude Haiku", 3, "premium_plus"),
        ("deepseek-v4-pro", "💎 DeepSeek Pro", 4, "premium_plus"),
    ],
    "image_generate": [
        ("flux-schnell", "⚡ Flux Schnell", 10, "free"),
        ("gpt-image-1-mini", "🖼️ GPT Image Mini", 10, "free"),
        ("gpt-image-2.5", "🎨 GPT Image 2.5", 35, "premium"),
        ("gpt-image-1.5", "🖼️ GPT Image 1.5", 40, "premium"),
        ("seedream-5-lite", "🌸 Seedream Lite", 135, "premium"),
        ("qwen-image-2512", "🟣 Qwen Image", 200, "premium_plus"),
    ],
}

MODEL_COSTS = {
    "gpt-4.1-nano": 1, "deepseek-v4-flash": 1,
    "gemini-2.5-flash-lite": 2, "qwen-3.6-flash": 2, "gpt-4.1-mini": 2,
    "claude-haiku": 3, "deepseek-v4-pro": 4,
    "flux-schnell": 10, "gpt-image-1-mini": 10,
    "gpt-image-2.5": 35, "gpt-image-1.5": 40,
    "seedream-5-lite": 135, "qwen-image-2512": 200,
}

MODEL_NAMES = {m[0]: m[1] for m in AVAILABLE_MODELS["text_chat"] + AVAILABLE_MODELS["image_generate"]}

DAILY_LIMITS = {"basic": 30, "premium": 100, "premium_plus": 300}

PLAN_LEVEL = {"basic": 0, "premium": 1, "premium_plus": 2}

MODEL_MIN_LEVEL = {
    "gpt-4.1-nano": 0, "deepseek-v4-flash": 0,
    "gemini-2.5-flash-lite": 1, "qwen-3.6-flash": 1, "gpt-4.1-mini": 1,
    "claude-haiku": 2, "deepseek-v4-pro": 2,
    "flux-schnell": 0, "gpt-image-1-mini": 0,
    "gpt-image-2.5": 1, "gpt-image-1.5": 1,
    "seedream-5-lite": 1, "qwen-image-2512": 2,
}


def model_choice_kb(task: str, current: str = None, plan: str = "basic", user_balance: int = 0):
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    models = AVAILABLE_MODELS.get(task, [])
    user_level = PLAN_LEVEL.get(plan, 0)

    for model_id, model_name, cost, min_plan in models:
        mark = "✅ " if model_id == current else ""
        cost_str = f" ({cost} ток.)"
        required_level = MODEL_MIN_LEVEL.get(model_id, 0)
        icon = " 🔒" if required_level > user_level else ""
        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{mark}{model_name}{cost_str}{icon}",
                callback_data=f"pickmodel|{task}|{model_id}"
            )
        ])
    kb.inline_keyboard.append([
        InlineKeyboardButton(text="🔒 Больше не спрашивать", callback_data=f"always|{task}")
    ])
    return kb


IMAGE_MODELS = {
    "flux-schnell": {"name": "⚡ Flux Schnell", "price": 10, "api_model": "flux-schnell"},
    "gpt-image-1-mini": {"name": "🖼️ GPT Image Mini", "price": 10, "api_model": "gpt-image-1-mini"},
    "gpt-image-2.5": {"name": "🎨 GPT Image 2.5", "price": 35, "api_model": "gpt-image-2.5"},
    "gpt-image-1.5": {"name": "🖼️ GPT Image 1.5", "price": 40, "api_model": "gpt-image-1.5"},
    "seedream-5-lite": {"name": "🌸 Seedream Lite", "price": 135, "api_model": "seedream-5-lite"},
    "qwen-image-2512": {"name": "🟣 Qwen Image", "price": 200, "api_model": "qwen-image-2512"},
}


def get_model_config(user_id):
    key = get_model_setting("image_generate") or "flux-schnell"
    return IMAGE_MODELS.get(key, IMAGE_MODELS["flux-schnell"])


def build_reminder_time(date_str, time_str):
    now = datetime.now()
    today = now.date()
    if not time_str:
        return None
    time_str = str(time_str).strip().lower()
    date_str = str(date_str or "").strip().lower()

    m = re.match(r'через\s+(\d+)\s*(мин|минут|час|часов|дн|дней|день)', time_str)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        if unit.startswith('мин'): return now + timedelta(minutes=amount)
        if unit.startswith('час'): return now + timedelta(hours=amount)
        if unit.startswith('дн'): return now + timedelta(days=amount)

    m = re.match(r'через\s+(\d+)$', time_str)
    if m:
        return now + timedelta(minutes=int(m.group(1)))

    time_str = time_str.replace(".", ":").replace(",", ":")
    m = re.match(r'^(\d{1,2}):(\d{2})$', time_str)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        time_obj = datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time()
        if date_str in (None, "", "today", "сегодня"):
            full = datetime.combine(today, time_obj)
            if full < now: full += timedelta(days=1)
            return full
        elif date_str in ("tomorrow", "завтра"):
            return datetime.combine(today + timedelta(days=1), time_obj)
        else:
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d").date()
                if d < today:
                    full = datetime.combine(today, time_obj)
                    if full < now: full += timedelta(days=1)
                    return full
                return datetime.combine(d, time_obj)
            except ValueError:
                return None
    return None
