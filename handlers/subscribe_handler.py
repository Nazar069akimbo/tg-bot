from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
import secrets
from datetime import datetime
from database.db import cursor, conn, add_premium, set_user_plan, get_user_plan
from backup_github import GitHubBackup
import logging

router = Router()
logger = logging.getLogger(__name__)

def get_subscribe_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ 49 Stars — 1 мес", callback_data="pay_1")],
            [InlineKeyboardButton(text="⭐ 129 Stars — 3 мес", callback_data="pay_3")],
            [InlineKeyboardButton(text="⭐ 249 Stars — 6 мес", callback_data="pay_6")],
            [InlineKeyboardButton(text="⭐ 449 Stars — 12 мес", callback_data="pay_12")],
            [InlineKeyboardButton(text="📊 Сменить план", callback_data="change_plan")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ]
    )

def get_plans_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Basic — 3 картинки/день (бесплатно)", callback_data="plan_basic")],
            [InlineKeyboardButton(text="💎 Premium — 50 картинок/день (49⭐/мес)", callback_data="plan_premium")],
            [InlineKeyboardButton(text="🔥 Pro — 200 картинок/день (99⭐/мес)", callback_data="plan_pro")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="premium")]
        ]
    )

@router.message(Command("subscribe"))
async def subscribe_cmd(message: types.Message):
    current_plan = get_user_plan(message.from_user.id)
    await message.answer(
        f"💎 **Premium подписка**\n\n"
        f"📊 Твой текущий план: {current_plan.upper()}\n\n"
        f"📋 **Планы:**\n"
        f"• Basic — 3 картинки/день (бесплатно)\n"
        f"• Premium — 50 картинок/день (49 ⭐/мес)\n"
        f"• Pro — 200 картинок/день (99 ⭐/мес)\n\n"
        f"💰 **Тарифы Premium:**\n"
        f"• 1 мес — 49 ⭐\n"
        f"• 3 мес — 129 ⭐\n"
        f"• 6 мес — 249 ⭐\n"
        f"• 12 мес — 449 ⭐\n\n"
        f"Выберите действие:",
        reply_markup=get_subscribe_kb()
    )

@router.callback_query(F.data == "premium")
async def premium_callback(callback: types.CallbackQuery):
    current_plan = get_user_plan(callback.from_user.id)
    await callback.message.edit_text(
        f"💎 **Premium подписка**\n\n"
        f"📊 Твой текущий план: {current_plan.upper()}\n\n"
        f"📋 **Планы:**\n"
        f"• Basic — 3 картинки/день (бесплатно)\n"
        f"• Premium — 50 картинок/день (49 ⭐/мес)\n"
        f"• Pro — 200 картинок/день (99 ⭐/мес)\n\n"
        f"💰 **Тарифы Premium:**\n"
        f"• 1 мес — 49 ⭐\n"
        f"• 3 мес — 129 ⭐\n"
        f"• 6 мес — 249 ⭐\n"
        f"• 12 мес — 449 ⭐\n\n"
        f"Выберите действие:",
        reply_markup=get_subscribe_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "change_plan")
async def change_plan(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "📊 **Смена плана**\n\n"
        "Выберите план:\n\n"
        "• Basic — 3 картинки/день (бесплатно)\n"
        "• Premium — 50 картинок/день (49⭐/мес)\n"
        "• Pro — 200 картинок/день (99⭐/мес)\n\n"
        "💰 Premium и Pro доступны после покупки Premium!",
        reply_markup=get_plans_kb()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("plan_"))
async def select_plan(callback: types.CallbackQuery):
    plan = callback.data.replace("plan_", "")
    
    plans = {
        'basic': {'price': '0 ⭐', 'images': '3'},
        'premium': {'price': '49 ⭐', 'images': '50'},
        'pro': {'price': '99 ⭐', 'images': '200'}
    }
    
    info = plans.get(plan, {})
    
    from database.db import is_premium
    has_premium = is_premium(callback.from_user.id)
    
    if plan != 'basic' and not has_premium:
        await callback.answer("❌ Купите Premium для этого плана!", show_alert=True)
        return
    
    set_user_plan(callback.from_user.id, plan)
    
    await callback.message.edit_text(
        f"✅ **План обновлён!**\n\n"
        f"📊 Твой план: {plan.upper()}\n"
        f"🖼️ Картинок в день: {info.get('images', '3')}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="premium")]]
        )
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
            description=f"Безлимит текста + картинки на {days} дней",
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
    set_user_plan(message.from_user.id, 'premium')
    
    try:
        backup = GitHubBackup()
        backup.backup_db(reason='покупка Premium')
    except Exception as e:
        logger.error(f"❌ Ошибка бэкапа: {e}")
    
    await message.answer(f"✅ Premium на {days} дней активирован!\n📊 План: PREMIUM — 50 картинок/день!")

@router.callback_query(F.data == "cancel_premium")
async def cancel_premium(callback: types.CallbackQuery):
    cursor.execute("UPDATE users SET premium_until = NULL, plan = 'basic' WHERE user_id = ?", (callback.from_user.id,))
    conn.commit()
    await callback.answer("✅ Premium отключён", show_alert=True)
    await callback.message.edit_text(
        "✅ **Premium отключён**\n\nТы вернулся на базовый план.\n3 картинки в день, 10 текстовых запросов.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="premium")]]
        )
    )
