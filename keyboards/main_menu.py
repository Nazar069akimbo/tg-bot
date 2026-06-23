from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def main_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🧠 Задать вопрос", callback_data="ask_question"),
                InlineKeyboardButton(text="🖼️ Сгенерировать картинку", callback_data="generate_image")
            ],
            [
                InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
                InlineKeyboardButton(text="📊 Статистика", callback_data="stats")
            ],
            [
                InlineKeyboardButton(text="👥 Рефералы", callback_data="referral"),
                InlineKeyboardButton(text="💎 Premium", callback_data="premium")
            ],
            [
                InlineKeyboardButton(text="📩 Обращение к админу", callback_data="contact_admin"),
                InlineKeyboardButton(text="❓ Помощь", callback_data="help")
            ],
            [
                InlineKeyboardButton(text="🏆 Рейтинг", callback_data="leaderboard"),
                InlineKeyboardButton(text="🛡️ Админ", callback_data="admin_panel")
            ]
        ]
    )
