from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def main_menu():
    """Главное меню"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📚 ГДЗ", callback_data="mode_gdz"), 
                InlineKeyboardButton(text="💬 Общение", callback_data="mode_chat")
            ],
            [
                InlineKeyboardButton(text="👤 Профиль", callback_data="profile"), 
                InlineKeyboardButton(text="📊 Статистика", callback_data="stats")
            ],
            [
                InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings"), 
                InlineKeyboardButton(text="👥 Рефералы", callback_data="referral")
            ],
            [
                InlineKeyboardButton(text="💎 Premium", callback_data="premium"), 
                InlineKeyboardButton(text="❓ Помощь", callback_data="help")
            ],
            [
                InlineKeyboardButton(text="🏆 Рейтинг", callback_data="leaderboard"),
                InlineKeyboardButton(text="🛡️ Админ", callback_data="admin_panel")
            ]
        ]
    )
