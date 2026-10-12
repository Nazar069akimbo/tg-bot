from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import (claim_daily_bonus, get_streak_info,
                          check_and_unlock_achievements, get_achievements,
                          achievements_list, get_tokens)
from . import helpers

router = Router()


def bonus_menu_kb(streak: int, claimed_today: bool):
    rows = []
    if claimed_today:
        rows.append([InlineKeyboardButton(text="✅ Уже получен сегодня", callback_data="noop")])
        rows.append([InlineKeyboardButton(text=f"🔥 Streak: {streak} дн.", callback_data="noop")])
    else:
        rows.append([InlineKeyboardButton(text="🎁 Забрать бонус", callback_data="claim_bonus")])
    rows.append([InlineKeyboardButton(text="🏆 Ачивки", callback_data="my_achievements")])
    rows.append([InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def show_bonus(message: types.Message, user_id: int = None):
    if user_id is None:
        user_id = message.from_user.id
    streak, last_date, claimed_today = get_streak_info(user_id)
    tokens = get_tokens(user_id)

    text = (
        "🎁 <b>Ежедневный бонус</b>\n\n"
        f"🔥 Streak: <b>{streak}</b> дн.\n"
        f"💰 Токенов: <b>{tokens}</b>\n\n"
    )

    if claimed_today:
        text += "✅ Бонус на сегодня уже получен.\nВозвращайся завтра!"
    else:
        bonus = min(5 + (streak // 7) * 5, 50) if streak else 5
        text += (
            f"📦 Следующий бонус: <b>+{bonus}</b> токенов\n\n"
            "🔥 Каждый день подряд = streak растёт!\n"
            "💎 Каждые 7 дней streak дают +5 токенов к бонусу."
        )

    try:
        await message.edit_text(text, reply_markup=bonus_menu_kb(streak, claimed_today))
    except Exception:
        await message.answer(text, reply_markup=bonus_menu_kb(streak, claimed_today))


@router.message(Command("bonus"))
async def bonus_cmd(message: types.Message):
    await show_bonus(message)


@router.callback_query(F.data == "daily_bonus")
async def bonus_cb(callback: types.CallbackQuery):
    await show_bonus(callback.message, callback.from_user.id)
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "claim_bonus")
async def claim_bonus_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    ok, amount, streak, already = claim_daily_bonus(user_id)

    if not ok and already:
        await helpers.safe_answer(callback, "✅ Уже получен сегодня", show_alert=True)
        return

    if not ok:
        await helpers.safe_answer(callback, "❌ Ошибка", show_alert=True)
        return

    # Проверяем ачивки
    new_ach = check_and_unlock_achievements(user_id)

    text = (
        f"🎁 <b>+{amount} токенов!</b>\n\n"
        f"🔥 Streak: <b>{streak}</b> дн.\n"
    )
    if streak >= 7:
        bonus_next = min(5 + ((streak + 1) // 7) * 5, 50)
        text += f"💎 Следующий бонус: +{bonus_next} токенов\n"

    if new_ach:
        ach_names = {c: (e, n) for c, e, n, _ in achievements_list()}
        text += "\n🏆 <b>Новые ачивки:</b>\n"
        for code in new_ach:
            e, n = ach_names.get(code, ("🏆", code))
            text += f"  {e} {n}\n"

    await callback.message.edit_text(text, reply_markup=bonus_menu_kb(streak, True))
    await helpers.safe_answer(callback, f"✅ +{amount} токенов!")


@router.callback_query(F.data == "my_achievements")
async def achievements_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    unlocked = get_achievements(user_id)

    text = "🏆 <b>Ачивки</b>\n\n"
    for code, emoji, name, desc in achievements_list():
        mark = "✅" if code in unlocked else "🔒"
        text += f"{mark} {emoji} <b>{name}</b>\n     <i>{desc}</i>\n"

    total = len(achievements_list())
    done = len(unlocked)
    text += f"\n📊 Открыто: <b>{done}/{total}</b>"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="daily_bonus")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await helpers.safe_answer(callback)


@router.callback_query(F.data == "noop")
async def noop_cb(callback: types.CallbackQuery):
    await helpers.safe_answer(callback)


async def notify_achievements(bot, user_id: int):
    """Вызывается после действий — проверяет новые ачивки и уведомляет."""
    try:
        new_ach = check_and_unlock_achievements(user_id)
        if not new_ach:
            return
        ach_names = {c: (e, n) for c, e, n, _ in achievements_list()}
        lines = []
        for code in new_ach:
            e, n = ach_names.get(code, ("🏆", code))
            lines.append(f"{e} <b>{n}</b>")
        if lines:
            await bot.send_message(
                user_id,
                "🏆 <b>Новая ачивка!</b>\n\n" + "\n".join(lines)
            )
    except Exception:
        pass
