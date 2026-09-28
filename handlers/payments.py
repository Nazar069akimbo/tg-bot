from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from . import helpers
from datetime import datetime
import secrets, logging, os, time, html as html_mod

router = Router()
logger = logging.getLogger(__name__)

PROVIDER_TOKEN = os.getenv('PROVIDER_TOKEN', '')

BOT_NAME = "Vertex AI"
TOKEN_ICON = "⭐"  # кастомный эмодзи недоступен в aiogram 3.5 — используем звезду

# Подписки: ключ -> (название, цена в ⭐, токенов-в-подарок, дней)
# Скидка premium на пакеты: -50%
PREMIUM_DISCOUNT = 0.5

SUBSCRIPTIONS = {
    'premium':       ("💎 Premium",      150, 3000, 30),
    'premium_plus':  ("👑 Premium+",     300, 8000, 30),
}

# Пакеты токенов: ключ -> (название, токенов, цена в ₽, цена в ⭐)
STAR_RATE = 0.45  # 1 ⭐ ≈ 0.45 ₽
TOKEN_PACKS = {
    'start':   ('Старт',    900, 100, round(100 / STAR_RATE)),
    'basic':   ('Базовый',  1800, 200, round(200 / STAR_RATE)),
    'value':   ('Выгодный', 2700, 290, round(290 / STAR_RATE)),
    'pro':     ('Профи',    3600, 390, round(390 / STAR_RATE)),
    'max':     ('Максимум', 4500, 490, round(490 / STAR_RATE)),
}
PACK_ORDER = list(TOKEN_PACKS.keys())


def is_premium(user_id) -> bool:
    """Активна ли подписка (по premium_until)."""
    try:
        user = get_user(user_id)
        if not user:
            return False
        plan = dict(user).get("plan") or "basic"
        until = dict(user).get("premium_until")
        if plan in ("premium", "premium_plus", "premium_deluxe") and until:
            return datetime.fromisoformat(until) > datetime.now()
    except Exception:
        pass
    return False


def premium_prices():
    """Цены пакетов со скидкой для premium."""
    return {
        key: (name, tokens, price, stars, round(price * (1 - PREMIUM_DISCOUNT)), round(stars * (1 - PREMIUM_DISCOUNT)))
        for key, (name, tokens, price, stars) in TOKEN_PACKS.items()
    }


def pack_price_for(user_id, key):
    """Итоговая цена пакета (в ⭐) с учётом скидки premium."""
    name, tokens, price, stars = TOKEN_PACKS[key]
    if is_premium(user_id):
        stars = round(stars * (1 - PREMIUM_DISCOUNT))
    return name, tokens, price, stars


async def show_screen(callback, text, kb):
    """new msg down on slow click; edit in place on fast series."""
    user_id = callback.from_user.id
    now = time.time()
    last = _last_screen_time.get(user_id, 0)
    if now - last < SCREEN_EDIT_SEC:
        try:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    _last_screen_time[user_id] = now
    await helpers.safe_answer(callback)


def esc(s):
    return html_mod.escape(str(s))


# ═══════════════════════════ СООБЩЕНИЕ «ЦЕНЫ» (как у Mira) ═══════════════════════════

PRICES_MENU_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🛒 Купить токены", callback_data="buy_tokens")],
    [InlineKeyboardButton(text="💎 Оформить Premium", callback_data="subscription")],
    [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")],
])


def prices_html(user_id: int) -> str:
    """Красивая HTML-разметка: Подписка Premium, пакеты со скидкой, стоимость генераций."""
    prem = esc(SUBSCRIPTIONS['premium'][1])  # 150⭐

    # — Пакеты таблицей: Пакет | Обычная цена | Для Premium (-50%) —
    rows = (
        "<code>Пакет      Токены   Обычная   Premium(-50%)</code>\n"
    )
    for key in PACK_ORDER:
        name, tokens, price, stars = TOKEN_PACKS[key]
        p_price = round(price * (1 - PREMIUM_DISCOUNT))
        name_pad = name.ljust(10)
        rows += (
            f"<code>{name_pad} {tokens:>4}   {price:>3}₽      {p_price}₽</code>\n"
        )

    return (
        f"<b>Цены {esc(BOT_NAME)}</b>\n"
        f"{'─' * 20}\n\n"
        f"<b>💎 Подписка Premium</b>\n"
        f"<blockquote>• Стоимость: <code>{prem} {TOKEN_ICON}</code> в месяц\n"
        f"• 🎁 Токены в подарок: <code>{SUBSCRIPTIONS['premium'][2]} {TOKEN_ICON}</code>\n"
        f"• 📈 Лимиты выше: больше генераций в день\n"
        f"• 💰 Скидка на пакеты: <b>-50%</b>\n"
        f"• 🎨 Премиум-модели изображений</blockquote>\n\n"
        f"<b>📦 Пакеты токенов (покупка без подписки)</b>\n"
        f"{rows}\n"
        f"<i>💡 Для Premium −50% на все пакеты</i>\n\n"
        f"{'─' * 20}\n\n"
        f"<b>🎛 Стоимость генераций (в токенах)</b>\n"
        f"▪️ 🖼 Картинка — <code>10 {TOKEN_ICON}</code>\n"
        f"▪️ 🎬 Видео — <code>50 {TOKEN_ICON}</code>\n"
        f"▪️ 🎵 Музыка — <code>30 {TOKEN_ICON}</code>\n"
        f"▪️ 🎭 Стикеры — <code>15 {TOKEN_ICON}</code>\n\n"
        f"{'─' * 20}\n"
        f"Купить можно через <code>/credits</code> или кнопку «Купить токены» 👇"
    )


async def send_prices(message: types.Message):
    user_id = message.from_user.id
    txt = prices_html(user_id)
    await message.answer(txt, reply_markup=PRICES_MENU_KB, parse_mode="HTML")


@router.message(Command("prices"))
async def prices_cmd(message: types.Message):
    await send_prices(message)


@router.callback_query(F.data == "prices")
async def prices_cb(callback: types.CallbackQuery):
    txt = prices_html(callback.from_user.id)
    await callback.message.edit_text(txt, reply_markup=PRICES_MENU_KB, parse_mode="HTML")
    await helpers.safe_answer(callback)


# ═══════════════════════════ ЭКРАН «Купить токены» ═══════════════════════════

async def buy_tokens_screen(callback=None, message=None):
    user_id = (callback.from_user.id if callback else message.from_user.id)
    prem = is_premium(user_id)
    kb_rows = []
    for key in PACK_ORDER:
        name, tokens, price, stars = TOKEN_PACKS[key]
        if prem:
            p_stars = round(stars * (1 - PREMIUM_DISCOUNT))
            label = f"{name} — {p_stars}{TOKEN_ICON} (-50%)"
        else:
            label = f"{name} — {stars}{TOKEN_ICON}"
        kb_rows.append([InlineKeyboardButton(text=label, callback_data=f"token_{key}")])
    kb_rows += [
        [InlineKeyboardButton(text="💎 Оформить Premium", callback_data="subscription")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")],
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    text = (
        f"<b>🛒 Купить токены</b>\n"
        f"{'─' * 20}\n"
        f"Сейчас: {'💎 Premium (скидка -50%)' if prem else '👤 Без подписки'}\n\n"
        f"{prices_small_table(prem)}\n"
        f"<i>Оплата в Telegram Stars ({TOKEN_ICON}). 1{TOKEN_ICON} ≈ 0.45₽</i>\n\n"
        f"Выбери пакет:"
    )
    if callback:
        await show_screen(callback, text, kb)
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


def prices_small_table(prem: bool) -> str:
    rows = "<code>Пакет      Токены   Цена</code>\n"
    for key in PACK_ORDER:
        name, tokens, price, stars = TOKEN_PACKS[key]
        if prem:
            price = round(price * (1 - PREMIUM_DISCOUNT))
        name_pad = name.ljust(10)
        rows += f"<code>{name_pad} {tokens:>4}   {price:>3}₽</code>\n"
    return rows


@router.callback_query(F.data == "buy_tokens")
async def buy_tokens_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    await buy_tokens_screen(callback=callback)


@router.message(Command("credits"))
async def credits_cmd(message: types.Message):
    await buy_tokens_screen(message=message)


# ═══════════════════════════ ПОДПИСКА ═══════════════════════════

@router.callback_query(F.data == "subscription")
async def subscription_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    prem = is_premium(user_id)
    kb_rows = [
        [InlineKeyboardButton(text=f"{name} — {stars}{TOKEN_ICON}/мес", callback_data=f"sub_{key}")]
        for key, (name, stars, _, _) in SUBSCRIPTIONS.items()
    ]
    if prem:
        kb_rows.append([InlineKeyboardButton(text="⏹ Отменить", callback_data="subscription_cancel")])
    kb_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="buy_tokens")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    text = (
        f"<b>💎 Подписка Premium</b>\n"
        f"{'─' * 20}\n\n"
        f"<blockquote>• 🎁 Токены в подарок сразу\n"
        f"• 📈 Лимиты выше\n"
        f"• 💰 Скидка -50% на пакеты\n"
        f"• 🎨 Премиум-модели</blockquote>\n\n"
        f"<b>Выбери тариф:</b>"
    )
    await show_screen(callback, text, kb)


@router.callback_query(F.data == "subscription_cancel")
async def subscription_cancel_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    update_premium_cancel(user_id)
    await callback.message.answer("✅ Подписка отменена", reply_markup=helpers.main_menu(), parse_mode="HTML")
    await helpers.safe_answer(callback)


# ═══════════════════════════ ОПЛАТА ═══════════════════════════

@router.callback_query(F.data.startswith("token_"))
async def token_pay_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    pack_type = callback.data.replace("token_", "")
    if pack_type not in TOKEN_PACKS:
        await helpers.safe_answer(callback, "❌ Неверный пакет", show_alert=True)
        return
    name, tokens, price_rub, stars = pack_price_for(user_id, pack_type)
    payload = secrets.token_hex(16)
    create_payment(user_id, stars, payload, "tokens")
    label = f"{name} · {tokens} токенов"
    if is_premium(user_id):
        label += " (−50% премиум)"
    await callback.bot.send_invoice(
        chat_id=user_id, title=label,
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
    if plan not in SUBSCRIPTIONS or not plan.startswith(("premium", "premium_plus")):
        await helpers.safe_answer(callback, "❌ Неверный тариф", show_alert=True)
        return
    plan_name, stars, bonus, days = SUBSCRIPTIONS[plan]
    payload = secrets.token_hex(16)
    create_payment(user_id, stars, payload, f"subscription_{plan}")
    await callback.bot.send_invoice(
        chat_id=user_id, title=f"{plan_name} · подписка",
        description=f"Подписка на {days} дней, {bonus} токенов в подарок",
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
            if plan_type in SUBSCRIPTIONS:
                plan_name, bonus_tokens, days = SUBSCRIPTIONS[plan_type][0], SUBSCRIPTIONS[plan_type][2], SUBSCRIPTIONS[plan_type][3]
                add_premium(message.from_user.id, days, plan_type, True)
                add_tokens(message.from_user.id, bonus_tokens)
                await message.answer(
                    f"✅ Подписка <b>{plan_name}</b> активирована!\n"
                    f"🎁 +{bonus_tokens} {TOKEN_ICON} в подарок",
                    reply_markup=helpers.main_menu(), parse_mode="HTML"
                )
                return
        if plan == "tokens":
            # Ищем пакет по уплаченной цене (в ⭐, с учётом скидки премиум)
            tokens = 0
            for key in PACK_ORDER:
                _, p_tokens, _, p_stars = pack_price_for(message.from_user.id, key)
                if p_stars == stars:
                    tokens = p_tokens
                    break
            if tokens > 0:
                add_tokens(message.from_user.id, tokens)
                await message.answer(f"✅ +{tokens} токенов!", reply_markup=helpers.main_menu(), parse_mode="HTML")
            else:
                await message.answer("❌ Ошибка")
        else:
            await message.answer("❌ Ошибка")
    else:
        await message.answer("❌ Ошибка")


def update_premium_cancel(user_id):
    """Отмена подписки (админ-хелпер): сбрасываем тариф."""
    try:
        from database.db import db_operation as _db_op
        import database.db as _db
        with _db.db_connection() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE users SET plan='basic', premium_until=NULL WHERE user_id=?", (user_id,))
    except Exception:
        pass
