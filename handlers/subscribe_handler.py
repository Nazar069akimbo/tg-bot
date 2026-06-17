from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
import secrets
from datetime import datetime
from database.db import cursor, conn, add_premium

router = Router()

def get_subscribe_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ 49 Stars — 1 мес", callback_data="pay_1")],
        [InlineKeyboardButton(text="⭐ 129 Stars — 3 мес", callback_data="pay_3")],
        [InlineKeyboardButton(text="⭐ 249 Stars — 6 мес", callback_data="pay_6")],
        [InlineKeyboardButton(text="⭐ 449 Stars — 12 мес", callback_data="pay_12")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

@router.message(Command("subscribe"))
async def subscribe_cmd(message: types.Message):
    await message.answer(
        "💎 **Premium подписка**\n\n"
        "• Безлимит задач\n"
        "• 3000 символов на запрос\n"
        "• Приоритетная обработка\n\n"
        "💰 **Тарифы:**\n"
        "• 1 мес — 49 ⭐\n"
        "• 3 мес — 129 ⭐\n"
        "• 6 мес — 249 ⭐\n"
        "• 12 мес — 449 ⭐\n\n"
        "Выберите тариф:",
        reply_markup=get_subscribe_kb()
    )

@router.callback_query(F.data == "premium")
async def premium_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "💎 **Premium подписка**\n\n"
        "• Безлимит задач\n"
        "• 3000 символов на запрос\n"
        "• Приоритетная обработка\n\n"
        "💰 **Тарифы:**\n"
        "• 1 мес — 49 ⭐\n"
        "• 3 мес — 129 ⭐\n"
        "• 6 мес — 249 ⭐\n"
        "• 12 мес — 449 ⭐\n\n"
        "Выберите тариф:",
        reply_markup=get_subscribe_kb()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("pay_"))
async def pay_callback(callback: types.CallbackQuery):
    try:
        plan = callback.data.replace("pay_", "")
        days = {"1": 30, "3": 90, "6": 180, "12": 365}[plan]
        stars = {"1": 49, "3": 129, "6": 249, "12": 449}[plan]
        payload = secrets.token_hex(16)
        
        cursor.execute(
            "INSERT INTO payments (user_id, stars_amount, telegram_payload, status, timestamp) VALUES (?, ?, ?, ?, ?)",
            (callback.from_user.id, stars, payload, "pending", datetime.now().isoformat())
        )
        conn.commit()
        
        await callback.bot.send_invoice(
            chat_id=callback.from_user.id,
            title=f"Premium {plan} мес",
            description=f"Безлимит задач на {days} дней",
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="Premium", amount=stars)],
            start_parameter="premium_sub"
        )
        await callback.answer()
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {str(e)}")
        await callback.answer()

@router.pre_checkout_query()
async def pre_checkout(query: types.PreCheckoutQuery):
    await query.answer(ok=True)

@router.message(F.successful_payment)
async def payment_success(message: types.Message):
    payload = message.successful_payment.invoice_payload
    
    cursor.execute("SELECT stars_amount FROM payments WHERE telegram_payload = ?", (payload,))
    row = cursor.fetchone()
    
    days = 30
    if row:
        stars = row[0]
        days = {49: 30, 129: 90, 249: 180, 449: 365}.get(stars, 30)
        cursor.execute("UPDATE payments SET status = 'completed' WHERE telegram_payload = ?", (payload,))
        conn.commit()
    
    add_premium(message.from_user.id, days)
    await message.answer(f"✅ Premium на {days} дней активирован! 🎉")
