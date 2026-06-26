from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import cursor, get_user
from keyboards import main_menu
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("referral"))
async def referral_cmd(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if not user:
        await message.answer("👋 Напишите /start для регистрации")
        return
    
    link = f"https://t.me/Vertex1bot?start={user_id}"
    
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
    
    text = f"👥 **Реферальная система**\n\n"
    text += f"📊 Приглашено: {count}\n"
    text += f"💰 Бонус: +5 запросов за каждого\n\n"
    text += f"🔗 Твоя ссылка:\n`{link}`\n\n"
    
    if referrals:
        text += "📋 **Приглашенные:**\n"
        for i, ref in enumerate(referrals[:5], 1):
            name = ref[1] or f"User_{ref[0]}"
            date = ref[2][:10] if ref[2] else "неизвестно"
            text += f"{i}. {name} — {date}\n"
        if len(referrals) > 5:
            text += f"\n... и еще {len(referrals) - 5} человек"
    else:
        text += "📋 **Приглашенных пока нет**\nПоделись ссылкой с друзьями!"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться ссылкой", callback_data="share_referral")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    
    await message.answer(text, reply_markup=kb)

@router.callback_query(F.data == "referral")
async def referral_callback(callback: types.CallbackQuery):
    try:
        logger.info(f"Referral callback from {callback.from_user.id}")
        
        user_id = callback.from_user.id
        user = get_user(user_id)
        
        if not user:
            await callback.message.edit_text("👋 Напишите /start для регистрации", reply_markup=main_menu())
            await callback.answer()
            return
        
        link = f"https://t.me/Vertex1bot?start={user_id}"
        
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
        
        text = f"👥 **Реферальная система**\n\n"
        text += f"📊 Приглашено: {count}\n"
        text += f"💰 Бонус: +5 запросов за каждого\n\n"
        text += f"🔗 Твоя ссылка:\n`{link}`\n\n"
        
        if referrals:
            text += "📋 **Приглашенные:**\n"
            for i, ref in enumerate(referrals[:5], 1):
                name = ref[1] or f"User_{ref[0]}"
                date = ref[2][:10] if ref[2] else "неизвестно"
                text += f"{i}. {name} — {date}\n"
            if len(referrals) > 5:
                text += f"\n... и еще {len(referrals) - 5} человек"
        else:
            text += "📋 **Приглашенных пока нет**\nПоделись ссылкой с друзьями!"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться ссылкой", callback_data="share_referral")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
        
        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()
    except Exception as e:
        logger.error(f"Referral callback error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data == "share_referral")
async def share_referral(callback: types.CallbackQuery):
    try:
        user_id = callback.from_user.id
        link = f"https://t.me/Vertex1bot?start={user_id}"
        
        share_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться", url=f"https://t.me/share/url?url={link}&text=🤖 Привет! Использую Vertex AI — мощный ИИ-помощник в Telegram! Присоединяйся! 🚀")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="referral")]
        ])
        
        await callback.message.edit_text(
            f"📤 **Поделиться ссылкой**\n\nНажми на кнопку ниже, чтобы отправить ссылку другу:\n\n`{link}`",
            reply_markup=share_kb
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Share referral error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
