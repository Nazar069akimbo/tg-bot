from aiogram import Router, types, F
from aiogram.types import LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from . import helpers
import secrets, logging, os

router = Router()
logger = logging.getLogger(__name__)

PROVIDER_TOKEN = os.getenv('PROVIDER_TOKEN', '')

@router.callback_query(F.data == "buy_tokens")
async def buy_tokens_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 50 токенов — 10⭐", callback_data="token_50")],
        [InlineKeyboardButton(text="📦 200 токенов — 30⭐", callback_data="token_200")],
        [InlineKeyboardButton(text="📦 500 токенов — 60⭐", callback_data="token_500")],
        [InlineKeyboardButton(text="📦 1000 токенов — 120⭐", callback_data="token_1000")],
        [InlineKeyboardButton(text="📦 2500 токенов — 250⭐", callback_data="token_2500")],
        [InlineKeyboardButton(text="👑 Подписка", callback_data="subscription")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    await callback.message.edit_text("✨ **Купить токены**\n\nВыбери пакет:", reply_markup=kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "subscription")
async def subscription_cb(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Премиум — 150⭐/мес", callback_data="sub_premium")],
        [InlineKeyboardButton(text="👑 Премиум+ — 300⭐/мес", callback_data="sub_premium_plus")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="buy_tokens")]
    ])
    await callback.message.edit_text("👑 **Подписки**\n\n💎 Премиум — 150⭐/мес\n👑 Премиум+ — 300⭐/мес", reply_markup=kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("token_"))
async def token_pay_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    packs = {'50': (10, 50), '200': (30, 200), '500': (60, 500), '1000': (120, 1000), '2500': (250, 2500)}
    pack_type = callback.data.replace("token_", "")
    if pack_type not in packs:
        await helpers.safe_answer(callback, "❌ Неверный пакет", show_alert=True)
        return
    stars, tokens = packs[pack_type]
    payload = secrets.token_hex(16)
    create_payment(user_id, stars, payload, "tokens")
    await callback.bot.send_invoice(
        chat_id=user_id, title=f"📦 {tokens} токенов",
        description=f"{tokens} токенов = {tokens//10} картинок",
        payload=payload, provider_token=PROVIDER_TOKEN, currency="XTR",
        prices=[LabeledPrice(label=f"{tokens} токенов", amount=stars)],
        start_parameter="buy_tokens"
    )
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("sub_"))
async def subscribe_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    plan = callback.data.replace("sub_", "")
    if plan == "premium":
        stars, plan_name = 150, "💎 Премиум"
    elif plan == "premium_plus":
        stars, plan_name = 300, "👑 Премиум+"
    else:
        await helpers.safe_answer(callback, "❌ Неверный тариф", show_alert=True)
        return
    payload = secrets.token_hex(16)
    create_payment(user_id, stars, payload, f"subscription_{plan}")
    await callback.bot.send_invoice(
        chat_id=user_id, title=plan_name,
        description="Подписка на 30 дней",
        payload=payload, provider_token=PROVIDER_TOKEN, currency="XTR",
        prices=[LabeledPrice(label=plan_name, amount=stars)],
        start_parameter="subscribe"
    )
    await helpers.safe_answer(callback)

@router.message(F.successful_payment)
async def payment_success(message: types.Message):
    payload = message.successful_payment.invoice_payload
    payment = complete_payment(payload)
    if payment:
        stars, plan = payment['stars_amount'], payment['plan']
        if plan.startswith("subscription_"):
            plan_type = plan.replace("subscription_", "")
            add_premium(message.from_user.id, 30, plan_type, True)
            await message.answer(f"✅ Подписка {plan_type} активирована!", reply_markup=helpers.main_menu())
            return
        if plan == "tokens":
            packs = {10: 50, 30: 200, 60: 500, 120: 1000, 250: 2500}
            tokens = packs.get(stars, 0)
            if tokens > 0:
                add_tokens(message.from_user.id, tokens)
                await message.answer(f"✅ +{tokens} токенов!", reply_markup=helpers.main_menu())
            else:
                await message.answer("❌ Ошибка")
        else:
            await message.answer("❌ Ошибка")
    else:
        await message.answer("❌ Ошибка")
