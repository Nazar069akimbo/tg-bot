from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import (claim_daily_bonus, get_streak_info,
                          check_and_unlock_achievements, get_achievements,
                          achievements_list, get_tokens, add_tokens)
from . import helpers

router = Router()


# Суммы награды за каждую ачивку (в токенах)
ACHIEVEMENT_REWARDS = {
    "first_step": 10,
    "week_active": 50,
    "month_active": 200,
    "artist_10": 30,
    "artist_100": 200,
    "artist_500": 1000,
    "talker_50": 50,
    "referrer_3": 100,
    "referrer_10": 500,
    "rich_1000": 0,  # уже богат, без награды
}


def bonus_menu_kb(streak: int, claimed_today: bool):
    rows = []
    if claimed_today:
        rows.append([InlineKeyboardButton(text="✅ Уже получен сегодня", callback_data="noop")])
        rows.append([InlineKeyboardButton(text=f"🔥 Streak: {streak} дн.", callback_data="noop")])
    else:
        rows.append([InlineKeyboardButton(text="🎁 Забрать бонус", callback_data="claim_bonus")])
    rows.append([InlineKeyboardButton(text="🏆 Мои ачивки", callback_data="my_achievements")])
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
            "🔥 Заходи каждый день — streak растёт!\n"
            "💎 Каждые 7 дней: +5 токенов к бонусу."
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
        text += "\n🏆 <b>Новые ачивки:</b>\n"
        ach_map = {c: (e, n) for c, e, n, _ in achievements_list()}
        for code in new_ach:
            e, n = ach_map.get(code, ("🏆", code))
            reward = ACHIEVEMENT_REWARDS.get(code, 0)
            text += f"  {e} <b>{n}</b>"
            if reward:
                text += f" +{reward} токенов"
                add_tokens(user_id, reward)
            text += "\n"

    await callback.message.edit_text(text, reply_markup=bonus_menu_kb(streak, True))
    await helpers.safe_answer(callback, f"✅ +{amount} токенов!")


@router.callback_query(F.data == "my_achievements")
async def achievements_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    unlocked = get_achievements(user_id)

    text = "🏆 <b>Ачивки</b>\n\n"
    for code, emoji, name, desc in achievements_list():
        mark = "✅" if code in unlocked else "🔒"
        reward = ACHIEVEMENT_REWARDS.get(code, 0)
        reward_str = f" — <b>+{reward} токенов</b>" if reward else ""
        text += f"{mark} {emoji} <b>{name}</b>{reward_str}\n     <i>{desc}</i>\n"

    total = len(achievements_list())
    done = len(unlocked)
    total_reward = sum(ACHIEVEMENT_REWARDS.get(c, 0) for c in unlocked)
    text += f"\n📊 Открыто: <b>{done}/{total}</b>"
    if total_reward:
        text += f"\n💰 Получено за ачивки: <b>{total_reward}</b> токенов"

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
    """Вызывается после действий. Проверяет новые ачивки, начисляет токены, уведомляет."""
    try:
        new_ach = check_and_unlock_achievements(user_id)
        if not new_ach:
            return
        ach_map = {c: (e, n) for c, e, n, _ in achievements_list()}
        lines = []
        total_reward = 0
        for code in new_ach:
            e, n = ach_map.get(code, ("🏆", code))
            reward = ACHIEVEMENT_REWARDS.get(code, 0)
            if reward:
                add_tokens(user_id, reward)
                total_reward += reward
                lines.append(f"{e} <b>{n}</b> — <b>+{reward} токенов</b>")
            else:
                lines.append(f"{e} <b>{n}</b>")

        if lines:
            msg = "🏆 <b>Новая ачивка!</b>\n\n" + "\n".join(lines)
            if total_reward:
                msg += f"\n\n💰 Итого: <b>+{total_reward}</b> токенов"
            await bot.send_message(user_id, msg)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"⚠️ notify_achievements: {e}")
