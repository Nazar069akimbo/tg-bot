from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import cursor, get_user
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("referral"))
async def referral_cmd(message: types.Message):
    user_id = message.from_user.id
    
    # Проверяем, существует ли пользователь
    user = get_user(user_id)
    if not user:
        await message.answer("👋 Напишите /start для регистрации")
        return
    
    # Генерируем реферальную ссылку
    link = f"https://t.me/ReshebnikPro_bot?start={user_id}"
    
    # Получаем количество рефералов (через приглашенных пользователей)
    cursor.execute("SELECT COUNT(*) FROM users WHERE username LIKE ?", (f"%{user_id}%",))
    # Простой подсчет - можно улучшить, добавив поле referrer_id в таблицу users
    # Пока просто показываем ссылку
    
    await message.answer(
        f"👥 **Реферальная система**\n\n"
        f"🔗 Ваша ссылка:\n"
        f"`{link}`\n\n"
        f"📋 **Как это работает:**\n"
        f"• Перешлите эту ссылку другу\n"
        f"• Когда друг перейдет по ссылке и запустит бота\n"
        f"• Вы получите **+5 бесплатных задач**!\n\n"
        f"💰 **Бонусы:**\n"
        f"• За каждого друга: +5 задач\n"
        f"• Безлимит рефералов\n"
        f"• Можно приглашать сколько угодно!\n\n"
        f"📤 Просто скопируй ссылку и отправь друзьям!",
        reply_markup=inline_kb()
    )

def inline_kb():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться ссылкой", callback_data="share_referral")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

@router.callback_query(F.data == "referral")
async def referral_callback(callback: types.CallbackQuery):
    try:
        user_id = callback.from_user.id
        link = f"https://t.me/ReshebnikPro_bot?start={user_id}"
        
        await callback.message.edit_text(
            f"👥 **Реферальная система**\n\n"
            f"🔗 Ваша ссылка:\n"
            f"`{link}`\n\n"
            f"📋 **Как это работает:**\n"
            f"• Перешлите эту ссылку другу\n"
            f"• Когда друг перейдет по ссылке и запустит бота\n"
            f"• Вы получите **+5 бесплатных задач**!\n\n"
            f"💰 **Бонусы:**\n"
            f"• За каждого друга: +5 задач\n"
            f"• Безлимит рефералов\n"
            f"• Можно приглашать сколько угодно!\n\n"
            f"📤 Просто скопируй ссылку и отправь друзьям!",
            reply_markup=inline_kb()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in referral callback: {e}")
        await callback.answer()

@router.callback_query(F.data == "share_referral")
async def share_referral(callback: types.CallbackQuery):
    try:
        user_id = callback.from_user.id
        link = f"https://t.me/ReshebnikPro_bot?start={user_id}"
        
        # Создаем кнопку для шаринга
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        share_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться", url=f"https://t.me/share/url?url={link}&text=Привет! Использую крутого бота для решения задач! Присоединяйся! 🚀")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="referral")]
        ])
        
        await callback.message.edit_text(
            f"📤 **Поделиться ссылкой**\n\n"
            f"Нажми на кнопку ниже, чтобы отправить ссылку другу:\n\n"
            f"`{link}`",
            reply_markup=share_kb
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in share_referral: {e}")
        await callback.answer()
