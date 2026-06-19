from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import cursor, get_user, conn
from keyboards import main_menu
import logging

router = Router()
logger = logging.getLogger(__name__)

# Проверяем, существует ли таблица referrals
def check_referrals_table():
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='referrals'")
    return cursor.fetchone() is not None

@router.message(Command("referral"))
async def referral_cmd(message: types.Message):
    user_id = message.from_user.id
    
    user = get_user(user_id)
    if not user:
        await message.answer(
            "👋 Напишите /start для регистрации",
            reply_markup=main_menu()
        )
        return
    
    # Проверяем таблицу
    if not check_referrals_table():
        await message.answer(
            "⚠️ Система рефералов временно недоступна. Попробуйте позже.",
            reply_markup=main_menu()
        )
        return
    
    # Считаем количество приглашенных
    cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
    count = cursor.fetchone()[0]
    
    # Получаем список приглашенных
    cursor.execute("""
        SELECT u.user_id, u.username, r.joined 
        FROM referrals r 
        JOIN users u ON r.referred_id = u.user_id 
        WHERE r.referrer_id = ? 
        ORDER BY r.joined DESC 
        LIMIT 10
    """, (user_id,))
    referrals = cursor.fetchall()
    
    link = f"https://t.me/VertexAIBot?start={user_id}"
    
    text = f"👥 **Реферальная система**\n\n"
    text += f"📊 Приглашено: {count}\n"
    text += f"💰 Бонус: +5 запросов за каждого\n\n"
    text += f"🔗 Ваша ссылка:\n`{link}`\n\n"
    
    if referrals:
        text += "📋 **Приглашенные:**\n"
        for i, ref in enumerate(referrals[:5], 1):
            name = ref[1] or f"User_{ref[0]}"
            date = ref[2][:10] if ref[2] else "неизвестно"
            text += f"{i}. {name} — {date}\n"
        if len(referrals) > 5:
            text += f"\n... и еще {len(referrals) - 5} человек"
    else:
        text += "📋 **Приглашенных пока нет**\n"
        text += "Поделись ссылкой с друзьями!"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться ссылкой", callback_data="share_referral")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    
    await message.answer(text, reply_markup=kb)

@router.callback_query(F.data == "referral")
async def referral_callback(callback: types.CallbackQuery):
    try:
        user_id = callback.from_user.id
        
        user = get_user(user_id)
        if not user:
            await callback.message.edit_text(
                "👋 Напишите /start для регистрации",
                reply_markup=main_menu()
            )
            await callback.answer()
            return
        
        if not check_referrals_table():
            await callback.message.edit_text(
                "⚠️ Система рефералов временно недоступна.",
                reply_markup=main_menu()
            )
            await callback.answer()
            return
        
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
        count = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT u.user_id, u.username, r.joined 
            FROM referrals r 
            JOIN users u ON r.referred_id = u.user_id 
            WHERE r.referrer_id = ? 
            ORDER BY r.joined DESC 
            LIMIT 10
        """, (user_id,))
        referrals = cursor.fetchall()
        
        link = f"https://t.me/VertexAIBot?start={user_id}"
        
        text = f"👥 **Реферальная система**\n\n"
        text += f"📊 Приглашено: {count}\n"
        text += f"💰 Бонус: +5 запросов за каждого\n\n"
        text += f"🔗 Ваша ссылка:\n`{link}`\n\n"
        
        if referrals:
            text += "📋 **Приглашенные:**\n"
            for i, ref in enumerate(referrals[:5], 1):
                name = ref[1] or f"User_{ref[0]}"
                date = ref[2][:10] if ref[2] else "неизвестно"
                text += f"{i}. {name} — {date}\n"
            if len(referrals) > 5:
                text += f"\n... и еще {len(referrals) - 5} человек"
        else:
            text += "📋 **Приглашенных пока нет**\n"
            text += "Поделись ссылкой с друзьями!"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться ссылкой", callback_data="share_referral")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
        
        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in referral callback: {e}")
        await callback.answer()

@router.callback_query(F.data == "share_referral")
async def share_referral(callback: types.CallbackQuery):
    try:
        user_id = callback.from_user.id
        link = f"https://t.me/VertexAIBot?start={user_id}"
        
        share_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться", url=f"https://t.me/share/url?url={link}&text=🤖 Привет! Использую Vertex AI — мощный ИИ-помощник в Telegram! Присоединяйся! 🚀")],
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

@router.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: types.CallbackQuery):
    from keyboards import main_menu
    await callback.message.edit_text(
        "🤖 **Vertex AI**\n\n"
        "🧠 Искусственный интеллект в твоем Telegram!\n\n"
        "✅ 10 запросов в день бесплатно\n"
        "💎 Premium: безлимит\n"
        "👥 Приведи друга → +5 запросов\n\n"
        "Просто напиши свой вопрос!",
        reply_markup=main_menu()
    )
    await callback.answer()
