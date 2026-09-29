from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from . import helpers
from datetime import datetime
import secrets, logging, os

router = Router()
logger = logging.getLogger(__name__)

PROVIDER_TOKEN = os.getenv('PROVIDER_TOKEN', '')


def is_premium(user_id) -> bool:
    try:
        user = get_user(user_id)
        if not user:
            return False
        user = dict(user)
        plan = user.get("plan") or "basic"
        until = user.get("premium_until")
        if plan in ("premium", "premium_plus") and until:
            return datetime.fromisoformat(until) > datetime.now()
    except Exception:
        pass
    return False


def prices_text() -> str:
    tokens_tariffs = get_tariffs("tokens")
    premium_tariffs = get_tariffs("premium")

    text = "💰 Цены Vertex AI\n\n"

    text += "📦 Пакеты токенов:\n"
    for t in tokens_tariffs:
        text += f"• {t['name']} — {t['price_rub']}₽ = {t['tokens']} токенов\n"
    text += "\n"

    if premium_tariffs:
        text += "💎 Подписки:\n"
        for t in premium_tariffs:
            text += f"• {t['name']} — {t['price_rub']}₽ / {t['days']} дней, +{t['tokens']} токенов\n"
        text += "\n"

    text += "🎛 Стоимость генераций:\n"
    text += "• 🖼 Картинка — 10 токенов\n"
    text += "• 🎨 Стикер — 10 токенов\n\n"

    text += "Оплата в Telegram Stars ⭐\n"
    text += "Купить: /credits или кнопка «Купить токены»"

    return text


def prices_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Купить токены", callback_data="buy_tokens")],
        [InlineKeyboardButton(text="💎 Подписки", callback_data="subscription")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")],
    ])


@router.message(Command("prices"))
async def prices_cmd(message: types.Message):
    await message.answer(prices_text(), reply_markup=prices_kb())


@router.callback_query(F.data == "prices")
async def prices_cb(callback: types.CallbackQuery):
    try:
        await callback.message.edit_text(prices_text(), reply_markup=prices_kb())
    except Exception:
        await callback.message.answer(prices_text(), reply_markup=prices_kb())
    await helpers.safe_answer(callback)


async def buy_tokens_screen(callback=None, message=None):
    user_id = (callback.from_user.id if callback else message.from_user.id)
    prem = is_premium(user_id)
    tariffs = get_tariffs("tokens")

    kb_rows = []
    for t in tariffs:
        label = f"{t['name']} — {t['price_rub']}₽ ({t['tokens']} токенов)"
        kb_rows.append([InlineKeyboardButton(text=label, callback_data=f"buy_tariff_{t['id']}")])
    kb_rows.append([InlineKeyboardButton(text="💎 Подписки", callback_data="subscription")])
    kb_rows.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    text = "🛒 Купить токены\n\n"
    text += "Выбери пакет — оплата в звёздах Telegram:\n\n"
    if prem:
        text += "💎 У тебя Premium — скидка 50% на пакеты!\n"
    for t in tariffs:
        text += f"• {t['name']} — {t['price_rub']}₽ = {t['tokens']} токенов\n"

    if callback:
        try:
            await callback.message.edit_text(text, reply_markup=kb)
        except Exception:
            await callback.message.answer(text, reply_markup=kb)
        await helpers.safe_answer(callback)
    else:
        await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "buy_tokens")
async def buy_tokens_cb(callback: types.CallbackQuery):
    force_create_user(callback.from_user.id, callback.from_user.username or "")
    await buy_tokens_screen(callback=callback)


@router.message(Command("credits"))
async def credits_cmd(message: types.Message):
    await buy_tokens_screen(message=message)


@router.callback_query(F.data.startswith("buy_tariff_"))
async def buy_tariff_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    try:
        tariff_id = int(callback.data.replace("buy_tariff_", ""))
    except ValueError:
        await helpers.safe_answer(callback, "❌ Ошибка", show_alert=True)
        return

    t = get_tariff(tariff_id)
    if not t:
        await helpers.safe_answer(callback, "❌ Тариф не найден", show_alert=True)
        return

    payload = secrets.token_hex(16)
    create_payment(user_id, t['stars'], payload, "tokens")

    label = f"{t['name']} · {t['tokens']} токенов"
    try:
        await callback.bot.send_invoice(
            chat_id=user_id,
            title=label,
            description=f"{t['tokens']} токенов = {t['tokens'] // 10} картинок",
            payload=payload,
            provider_token=PROVIDER_TOKEN,
            currency="XTR",
            prices=[LabeledPrice(label=f"{t['tokens']} токенов", amount=t['stars'])],
            start_parameter="buy_tokens"
        )
    except Exception as e:
        logger.error(f"Ошибка инвойса: {e}")
        await helpers.safe_answer(callback, "❌ Ошибка оплаты", show_alert=True)
        return
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "subscription")
async def subscription_cb(callback: types.CallbackQuery):
    tariffs = get_tariffs("premium")
    kb_rows = []
    for t in tariffs:
        kb_rows.append([InlineKeyboardButton(
            text=f"{t['name']} — {t['price_rub']}₽ / {t['days']} дн",
            callback_data=f"sub_tariff_{t['id']}"
        )])
    kb_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="buy_tokens")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    text = "💎 Подписки\n\n"
    for t in tariffs:
        text += f"• {t['name']} — {t['price_rub']}₽ / {t['days']} дней\n"
        text += f"  +{t['tokens']} токенов в подарок\n"
    text += "\nВыбери тариф:"

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await helpers.safe_answer(callback)


@router.callback_query(F.data.startswith("sub_tariff_"))
async def sub_tariff_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    try:
        tariff_id = int(callback.data.replace("sub_tariff_", ""))
    except ValueError:
        await helpers.safe_answer(callback, "❌ Ошибка", show_alert=True)
        return

    t = get_tariff(tariff_id)
    if not t:
        await helpers.safe_answer(callback, "❌ Тариф не найден", show_alert=True)
        return

    payload = secrets.token_hex(16)
    create_payment(user_id, t['stars'], payload, f"subscription_{tariff_id}")

    try:
        await callback.bot.send_invoice(
            chat_id=user_id,
            title=f"{t['name']} · подписка",
            description=f"Подписка на {t['days']} дней, {t['tokens']} токенов в подарок",
            payload=payload,
            provider_token=PROVIDER_TOKEN,
            currency="XTR",
            prices=[LabeledPrice(label=t['name'], amount=t['stars'])],
            start_parameter="subscribe"
        )
    except Exception as e:
        logger.error(f"Ошибка инвойса: {e}")
        await helpers.safe_answer(callback, "❌ Ошибка оплаты", show_alert=True)
        return
    await helpers.safe_answer(callback)


@router.message(F.successful_payment)
async def payment_success(message: types.Message):
    payload = message.successful_payment.invoice_payload
    payment = complete_payment(payload)
    if not payment:
        await message.answer("❌ Ошибка оплаты")
        return

    plan = payment['plan']
    user_id = message.from_user.id

    if plan.startswith("subscription_"):
        try:
            tariff_id = int(plan.replace("subscription_", ""))
        except ValueError:
            await message.answer("❌ Ошибка тарифа")
            return

        t = get_tariff(tariff_id)
        if not t:
            await message.answer("❌ Тариф не найден")
            return

        add_premium(user_id, t['days'], "premium", True)
        add_tokens(user_id, t['tokens'])
        await message.answer(
            f"✅ Подписка {t['name']} активирована!\n"
            f"🎁 +{t['tokens']} токенов в подарок",
            reply_markup=helpers.main_menu()
        )
        return

    if plan == "tokens":
        stars_paid = payment['stars_amount']
        tokens = 0
        for t in get_tariffs("tokens"):
            if t['stars'] == stars_paid:
                tokens = t['tokens']
                break
        if tokens > 0:
            add_tokens(user_id, tokens)
            await message.answer(f"✅ +{tokens} токенов!", reply_markup=helpers.main_menu())
        else:
            await message.answer("❌ Ошибка начисления")
        return

    await message.answer("❌ Неизвестный платёж")
