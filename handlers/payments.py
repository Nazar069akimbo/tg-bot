from aiogram import Router, types, F
from aiogram.types import LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from . import helpers
import secrets, logging, os

router = Router()
logger = logging.getLogger(__name__)

PROVIDER_TOKEN = os.getenv('PROVIDER_TOKEN', '')

# Пакеты токенов: ключ -> (название пакета, токенов, цена в ₽, цена в ⭐)
STAR_RATE = 0.45  # 1 ⭐ ≈ 0.45 ₽
TOKEN_PACKS = {
    'start':   ('🚀 Старт',    900, 100, round(100 / STAR_RATE)),
    'basic':   ('📦 Базовый',  1800, 200, round(200 / STAR_RATE)),
    'value':   ('🎁 Выгодный', 2700, 290, round(290 / STAR_RATE)),
    'pro':     ('💎 Профи',    3600, 390, round(390 / STAR_RATE)),
    'max':     ('👑 Максимум', 4500, 490, round(490 / STAR_RATE)),
}

@router.callback_query(F.data == "buy_tokens")
async def buy_tokens_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{name} · {tokens} ток · {price}₽ / {stars}⭐",
            callback_data=f"token_{key}"
        )]
        for key, (name, tokens, price, stars) in TOKEN_PACKS.items()
    ] + [
        [InlineKeyboardButton(text="👑 Подписка", callback_data="subscription")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(
        "✨ **Купить токены**\n\n"
        "💳 Оплата в Telegram Stars (⭐)\n"
        "💡 1⭐ ≈ 0.45 ₽\n\n"
        "Выбери пакет:",
        reply_markup=kb
    )
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
    pack_type = callback.data.replace("token_", "")
    if pack_type not in TOKEN_PACKS:
        await helpers.safe_answer(callback, "❌ Неверный пакет", show_alert=True)
        return
    name, tokens, price_rub, stars = TOKEN_PACKS[pack_type]
    payload = secrets.token_hex(16)
    create_payment(user_id, stars, payload, "tokens")
    await callback.bot.send_invoice(
        chat_id=user_id, title=f"{name} · {tokens} токенов",
        description=f"{tokens} токенов = {tokens//10} картинок · ≈{price_rub}₽",
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
            # Находим пакет по цене в ⭐
            tokens = 0
            for key, (pname, p_tokens, p_rub, p_stars) in TOKEN_PACKS.items():
                if p_stars == stars:
                    tokens = p_tokens
                    break
            if tokens > 0:
                add_tokens(message.from_user.id, tokens)
                await message.answer(f"✅ +{tokens} токенов!", reply_markup=helpers.main_menu())
            else:
                await message.answer("❌ Ошибка")
        else:
            await message.answer("❌ Ошибка")
    else:
        await message.answer("❌ Ошибка")
