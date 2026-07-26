from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, BufferedInputFile
from database.db import *
from ai.client import solve_problem
from backup import GitHubBackup
import logging, secrets, os, requests, asyncio
from datetime import datetime, timedelta
from io import BytesIO
import matplotlib.pyplot as plt
import csv
from io import StringIO

router = Router()
logger = logging.getLogger(__name__)
user_modes = {}
user_pages = {}
ADMIN_CODE = "30121979"
API_KEY = os.getenv('OPENAI_API_KEY')
IMAGE_MODEL = "flux-schnell"
PROMPT_MODEL = "gpt-4.1-nano"

plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['font.size'] = 10

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def force_create_user(user_id, username=None):
    try:
        user = get_user(user_id)
        if user:
            if user['plan'] == 'basic' and user['premium_until'] and user['premium_until'] > datetime.now().isoformat():
                from database.db import get_db
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE users SET plan = 'premium' WHERE user_id = ?", (user_id,))
                user = get_user(user_id)
            return user
        result = create_user(user_id, username or str(user_id))
        if result:
            user = get_user(user_id)
            if user:
                return user
        return None
    except:
        return None

def do_backup():
    try:
        GitHubBackup().backup_db()
    except:
        pass

def get_plan_emoji(plan):
    if plan == 'premium_deluxe':
        return "👑 Premium Deluxe"
    elif plan == 'premium':
        return "💎 Premium"
    else:
        return "🔴 Бесплатный"

# ========== МЕНЮ ==========
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧠 Текст", callback_data="mode_text"), InlineKeyboardButton(text="🖼️ Картинка", callback_data="mode_image")],
        [InlineKeyboardButton(text="📅 Бонус дня", callback_data="daily_bonus"), InlineKeyboardButton(text="💎 Premium", callback_data="premium")],
        [InlineKeyboardButton(text="👥 Рефералы", callback_data="referral"), InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats"), InlineKeyboardButton(text="📩 Поддержка", callback_data="contact_admin")],
        [InlineKeyboardButton(text="🏆 Рейтинг", callback_data="leaderboard"), InlineKeyboardButton(text="🛡️ Админ", callback_data="admin_panel")],
        [InlineKeyboardButton(text="🎁 Промокод", callback_data="promo_use"), InlineKeyboardButton(text="📋 Мои бонусы", callback_data="my_bonus")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ])

def admin_kb():
    new_messages = get_messages_count()
    badge = f" ({new_messages})" if new_messages > 0 else ""
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM emails WHERE receiver_id = ? AND is_read = 0", (6957852385,))
        new_emails = cursor.fetchone()[0] or 0
    email_badge = f" ({new_emails})" if new_emails > 0 else ""
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="a_stats"), InlineKeyboardButton(text="📈 График", callback_data="a_chart")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="a_users"), InlineKeyboardButton(text="💎 Выдать Premium", callback_data="a_give_premium")],
        [InlineKeyboardButton(text="🔄 Сменить тариф", callback_data="a_change_plan")],
        [InlineKeyboardButton(text=f"📩 Обращения{badge}", callback_data="a_messages")],
        [InlineKeyboardButton(text="📧 Почта{email_badge}", callback_data="a_email"), InlineKeyboardButton(text="⚙️ Тарифы", callback_data="a_plans")],
        [InlineKeyboardButton(text="🚫 Блокировка", callback_data="a_block"), InlineKeyboardButton(text="📢 Рассылка", callback_data="a_broadcast")],
        [InlineKeyboardButton(text="💾 Бэкап", callback_data="a_backup"), InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

# ========== КОМАНДЫ ПОЛЬЗОВАТЕЛЯ ==========
@router.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    user = force_create_user(user_id, username)
    if not user:
        await message.answer("❌ Ошибка регистрации.")
        return
    if not user['username'] or user['username'] == str(user_id):
        user_pages[user_id] = {"state": "waiting_name"}
        await message.answer("👋 Привет! Как мне тебя называть?\nНапиши своё имя:")
        return
    args = message.text.split() if message.text else []
    if len(args) > 1 and args[1].isdigit():
        referrer_id = int(args[1])
        if referrer_id != user_id:
            success, msg = add_referral(referrer_id, user_id)
            if success:
                await message.answer(msg)
    text = (
        "🤖 **Vertex AI**\n\n"
        "Искусственный интеллект в Telegram!\n\n"
        "🔴 Бесплатно: 10 запросов/день + 3 картинки\n"
        "💎 Premium: безлимит + 50 картинок/день (49⭐/мес)\n"
        "👑 Premium Deluxe: безлимит + 200 картинок/день (99⭐/мес)\n\n"
        "📅 Ежедневный бонус: нажми 'Бонус дня'\n"
        "👥 Приведи друга: +3 картинки и +10 запросов\n\n"
        "✏️ Просто напиши свой вопрос!"
    )
    await message.answer(text, reply_markup=main_menu())

@router.message(Command("daily"))
async def daily_cmd(message: types.Message):
    user_id = message.from_user.id
    user = force_create_user(user_id, message.from_user.username or "")
    if not user:
        await message.answer("❌ Ошибка! Попробуйте позже.", reply_markup=main_menu())
        return
    success, streak, msg = do_daily_checkin(user_id)
    await message.answer(msg, reply_markup=main_menu())

@router.message(Command("stats"))
async def stats_cmd(message: types.Message):
    user_id = message.from_user.id
    user = force_create_user(user_id, message.from_user.username or "")
    if not user:
        await message.answer("❌ Ошибка!", reply_markup=main_menu())
        return
    used, limit, prem, plan_from_stats, bonus_img = get_image_stats(user_id)
    total_requests = user['total_requests'] if user['total_requests'] else 0
    total_images = user['image_requests'] if user['image_requests'] else 0
    streak = user['checkin_streak'] if user['checkin_streak'] else 0
    b_img, b_req = get_bonus_balance(user_id)
    plan = user['plan'] if user['plan'] else 'basic'
    plan_names = {'basic': '🔴 Бесплатный', 'premium': '💎 Premium', 'premium_deluxe': '👑 Premium Deluxe'}
    text = (
        "📊 **Статистика**\n\n"
        f"📝 Запросов: {total_requests}\n"
        f"🖼️ Картинок: {total_images}\n"
        f"📅 Сегодня: {used}/{limit}\n"
        f"🎁 Бонусов: {b_img} картинок, {b_req} запросов\n"
        f"🔥 Серия бонусов: {streak} дней\n"
        f"💎 План: {plan_names.get(plan, '🔴 Бесплатный')}"
    )
    await message.answer(text, reply_markup=main_menu())

@router.message(Command("profile"))
async def profile_cmd(message: types.Message):
    user_id = message.from_user.id
    user = force_create_user(user_id, message.from_user.username or "")
    if not user:
        await message.answer("❌ Ошибка!", reply_markup=main_menu())
        return
    plan_emoji = get_plan_emoji(user['plan'] if user['plan'] else 'basic')
    text = (
        f"👤 **Мой профиль**\n\n"
        f"🆔 ID: {user['user_id']}\n"
        f"👤 Имя: {user['username'] or 'без имени'}\n"
        f"💎 План: {plan_emoji}\n"
        f"📆 Регистрация: {user['joined'][:10] if user['joined'] else 'Нет'}"
    )
    await message.answer(text, reply_markup=main_menu())

@router.message(Command("premium"))
async def premium_cmd(message: types.Message):
    user_id = message.from_user.id
    force_create_user(user_id, message.from_user.username or "")
    text = (
        "💎 **Premium**\n\n"
        "🔴 Бесплатный — 0⭐\n"
        "• 10 текстовых запросов/день\n"
        "• 3 картинки/день\n\n"
        "💎 Premium — 49⭐/мес\n"
        "• Безлимит текста\n"
        "• 50 картинок/день\n"
        "• Приоритетная обработка\n\n"
        "👑 Premium Deluxe — 99⭐/мес\n"
        "• Безлимит текста\n"
        "• 200 картинок/день\n"
        "• VIP-поддержка\n\n"
        "📦 **Планы на 3, 6, 12 месяцев со скидкой!**"
    )
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 1 мес 49⭐", callback_data="pay_premium_1m"), InlineKeyboardButton(text="💎 3 мес 129⭐", callback_data="pay_premium_3m")],
            [InlineKeyboardButton(text="💎 6 мес 249⭐", callback_data="pay_premium_6m"), InlineKeyboardButton(text="💎 12 мес 449⭐", callback_data="pay_premium_12m")],
            [InlineKeyboardButton(text="👑 1 мес 99⭐", callback_data="pay_deluxe_1m"), InlineKeyboardButton(text="👑 3 мес 269⭐", callback_data="pay_deluxe_3m")],
            [InlineKeyboardButton(text="👑 6 мес 499⭐", callback_data="pay_deluxe_6m"), InlineKeyboardButton(text="👑 12 мес 899⭐", callback_data="pay_deluxe_12m")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
    )

@router.message(Command("referral"))
async def referral_cmd(message: types.Message):
    user_id = message.from_user.id
    user = force_create_user(user_id, message.from_user.username or "")
    if not user:
        await message.answer("❌ Ошибка!", reply_markup=main_menu())
        return
    count = get_referral_count(user_id)
    bonus_images, bonus_requests = get_referral_bonuses(user_id)
    link = f"https://t.me/Vertex1bot?start={user_id}"
    text = (
        "👥 **Рефералы**\n\n"
        f"👤 Приглашено: {count}\n"
        f"🎁 Бонусы: +{bonus_images} карт, +{bonus_requests} запросов\n\n"
        f"🔗 Твоя ссылка:\n{link}"
    )
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться", url=f"https://t.me/share/url?url={link}&text=🤖 Присоединяйся к Vertex AI!")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
    )

@router.message(Command("help"))
async def help_cmd(message: types.Message):
    text = (
        "❓ **Помощь**\n\n"
        "🧠 Текст — просто напиши вопрос\n"
        "🖼️ Картинка — нажми кнопку и опиши\n"
        "📅 Бонус дня — получай бонусы каждый день\n"
        "👥 Рефералы — приглашай друзей\n"
        "💎 Premium — безлимит\n\n"
        "📌 Команды:\n"
        "/start — меню\n"
        "/profile — профиль\n"
        "/stats — статистика\n"
        "/daily — бонус дня\n"
        "/premium — Premium\n"
        "/referral — рефералы"
    )
    await message.answer(text, reply_markup=main_menu())

@router.message(Command("leaderboard"))
async def leaderboard_cmd(message: types.Message):
    user_id = message.from_user.id
    force_create_user(user_id, message.from_user.username or "")
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, total_requests FROM users ORDER BY total_requests DESC LIMIT 10")
        users = cursor.fetchall()
    if not users:
        return await message.answer("🏆 Нет данных", reply_markup=main_menu())
    medals = ['🥇', '🥈', '🥉']
    text = "🏆 **Рейтинг**\n\n"
    for i, u in enumerate(users):
        medal = medals[i] if i < 3 else f"{i+1}."
        name = u['username'] if u['username'] else str(u['user_id'])
        text += f"{medal} {name} — {u['total_requests']} задач\n"
    await message.answer(text, reply_markup=main_menu())

@router.message(Command("contact_admin"))
async def contact_admin_cmd(message: types.Message):
    user_id = message.from_user.id
    force_create_user(user_id, message.from_user.username or "")
    user_pages[user_id] = {"state": "waiting_contact"}
    await message.answer("📩 Напишите сообщение админу.\n\n⏹ /cancel", reply_markup=main_menu())

@router.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if is_admin(message.from_user.id):
        await message.answer("🛡️ **АДМИН-ПАНЕЛЬ**", reply_markup=admin_kb())
    else:
        await message.answer("🔐 Введите код: /admin_code 30121979")

@router.message(Command("admin_code"))
async def admin_code_cmd(message: types.Message):
    args = message.text.split() if message.text else []
    if len(args) > 1 and args[1] == ADMIN_CODE:
        add_admin(message.from_user.id)
        await message.answer("✅ Вы админ!", reply_markup=admin_kb())

@router.message(Command("cancel"))
async def cancel_cmd(message: types.Message):
    user_pages.pop(message.from_user.id, None)
    await message.answer("✅ Отменено", reply_markup=main_menu())

@router.message(Command("set_plan"))
async def set_plan_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        return
    try:
        parts = message.text.split() if message.text else []
        if len(parts) < 3:
            await message.answer("❌ Использование: /set_plan ID premium|premium_deluxe|basic")
            return
        user_id = int(parts[1])
        plan = parts[2].lower()
        if plan not in ['premium', 'premium_deluxe', 'basic']:
            await message.answer("❌ План: premium, premium_deluxe или basic")
            return
        if plan == 'basic':
            remove_premium(user_id)
            await message.answer(f"✅ Basic восстановлен для {user_id}")
        else:
            success = add_premium(user_id, 30, plan, paid=True)
            if success:
                plan_names = {'premium': '💎 Premium', 'premium_deluxe': '👑 Premium Deluxe'}
                await message.answer(f"✅ {plan_names.get(plan, plan)} на 30 дней выдан {user_id}")
            else:
                await message.answer(f"❌ Ошибка выдачи Premium пользователю {user_id}")
        do_backup()
    except ValueError:
        await message.answer("❌ ID должен быть числом")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

# ========== ОБРАБОТКА ТЕКСТА ==========
@router.message(F.text)
async def handle_message(message: types.Message):
    if not message.text or message.text.startswith("/"):
        return
    user_id = message.from_user.id
    state = user_pages.get(user_id, {})
    
    if state.get("state") == "waiting_name":
        from database.db import get_db
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (message.text, user_id))
        user_pages.pop(user_id, None)
        await message.answer(f"✅ Отлично, {message.text}! Теперь я запомнил тебя.")
        await start_cmd(message)
        return
    
    if state.get("state") == "waiting_promo_use":
        success, msg = use_promocode(message.text.upper(), user_id)
        await message.answer(msg, reply_markup=main_menu())
        user_pages.pop(user_id, None)
        return
    
    if state.get("state") in ["waiting_plan_edit", "waiting_premium_user", "waiting_broadcast", "waiting_block_user", "waiting_contact", "waiting_reply", "waiting_change_plan", "waiting_promo", "waiting_bonus"]:
        await handle_admin_input(message)
        return
    
    user = force_create_user(user_id, message.from_user.username or "")
    if not user:
        await message.answer("❌ Ошибка! Попробуйте позже.", reply_markup=main_menu())
        return
    
    mode = user_modes.get(user_id, "text")
    if mode == "image":
        await generate_image(message)
    else:
        await generate_text(message)

async def generate_text(message: types.Message):
    user_id = message.from_user.id
    ok, rem, bonus_req = can_request(user_id)
    if not ok:
        return await message.answer("🔒 Лимит исчерпан! /premium")
    prem = is_premium(user_id)
    status_msg = await message.answer("🤔 Думаю...")
    try:
        from ai.client import solve_problem
        answer = solve_problem(message.text, "chat", prem)
        add_request(user_id)
        do_backup()
        if prem:
            remaining = "♾️ Безлимит"
        else:
            remaining = f"📊 Осталось {rem-1} запросов"
        await status_msg.edit_text(f"🧠 {answer}\n\n{remaining}")
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def generate_image(message: types.Message):
    user_id = message.from_user.id
    if not API_KEY:
        return await message.answer("❌ API ключ не настроен")
    user = get_user(user_id)
    if not user:
        return await message.answer("❌ Ошибка! Пользователь не найден.")
    trial_rem = get_trial_remaining(user_id)
    used, limit, prem, plan, bonus_img = get_image_stats(user_id)
    if prem:
        can_gen = True
    elif trial_rem > 0:
        can_gen = True
        limit = 5
    else:
        can_gen, _, _ = can_generate_image(user_id)
    if not can_gen:
        return await message.answer(f"❌ Лимит картинок! {used}/{limit}\n💎 /premium")
    status_msg = await message.answer("🎨 Генерирую...")
    try:
        user_prompt = message.text
        prompt_resp = requests.post(
            "https://openai.bothub.chat/v1/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={"model": PROMPT_MODEL, "messages": [{"role": "system", "content": "Create detailed English prompt for Flux. Only the prompt!"}, {"role": "user", "content": f"Prompt for: {user_prompt}"}], "max_tokens": 200},
            timeout=30
        )
        enhanced = user_prompt
        if prompt_resp.status_code == 200:
            enhanced = prompt_resp.json().get('choices', [{}])[0].get('message', {}).get('content', user_prompt).strip('"')
        for p in range(5, 101, 5):
            await asyncio.sleep(0.3)
            try:
                await status_msg.edit_text(f"🎨 {p}%")
            except:
                pass
        img_resp = requests.post(
            "https://bothub.chat/api/v2/replicate/v1/images/generations",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={"model": IMAGE_MODEL, "input": {"prompt": enhanced, "aspect_ratio": "1:1", "output_format": "webp"}, "bothub": {"include_usage": True, "return_base64": False}},
            timeout=120
        )
        if img_resp.status_code == 200:
            result = img_resp.json()
            img_url = result.get('url')
            if isinstance(img_url, list):
                img_url = img_url[0]
            if img_url:
                img_data = requests.get(img_url, timeout=30)
                if img_data.status_code == 200 and len(img_data.content) > 1000:
                    await status_msg.edit_text("🎨 100% ✅")
                    await asyncio.sleep(0.2)
                    if trial_rem > 0:
                        use_trial_image(user_id)
                    else:
                        add_image_request(user_id)
                    do_backup()
                    new_used, new_limit, new_prem, new_plan, new_bonus = get_image_stats(user_id)
                    user_plan = user['plan'] if user['plan'] else 'basic'
                    plan_emoji = get_plan_emoji(user_plan)
                    remaining = new_limit - new_used
                    await message.answer_photo(
                        BufferedInputFile(file=img_data.content, filename="image.webp"),
                        caption=f"🖼️ **Твоя картинка**\n📝 {user_prompt[:50]}...\n\n📊 Осталось картинок: {remaining}\n🎁 Бонусных: {new_bonus}\n💎 План: {plan_emoji}"
                    )
                    await status_msg.delete()
                    return
        await status_msg.edit_text("❌ Не удалось получить картинку")
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

# ========== CALLBACK'И ПОЛЬЗОВАТЕЛЕЙ ==========
@router.callback_query(F.data.in_(["mode_text", "mode_image"]))
async def set_mode(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    mode = callback.data.replace("mode_", "")
    user_modes[user_id] = mode
    await callback.answer(f"✅ Режим: {'🧠 Текст' if mode == 'text' else '🖼️ Картинка'}", show_alert=True)
    await callback.message.edit_text(f"{'🧠 Текст' if mode == 'text' else '🖼️ Картинка'}\n\nГотов к работе!", reply_markup=main_menu())

@router.callback_query(F.data == "daily_bonus")
async def daily_bonus_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = force_create_user(user_id, callback.from_user.username or "")
    if not user:
        await callback.answer("❌ Ошибка!", show_alert=True)
        return
    success, streak, msg = do_daily_checkin(user_id)
    await callback.message.edit_text(msg, reply_markup=main_menu())
    await callback.answer()

@router.callback_query(F.data == "stats")
async def stats_cb(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    user = force_create_user(user_id, callback.from_user.username or "")
    if not user:
        return
    class FakeMessage:
        def __init__(self, uid, username):
            self.from_user = type('obj', (object,), {'id': uid, 'username': username})()
            self.text = ""
            self.answer = callback.message.answer
            self.reply_markup = callback.message.reply_markup
    fake_msg = FakeMessage(user_id, callback.from_user.username or "")
    await stats_cmd(fake_msg)

@router.callback_query(F.data == "profile")
async def profile_cb(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    user = force_create_user(user_id, callback.from_user.username or "")
    if not user:
        return
    class FakeMessage:
        def __init__(self, uid, username):
            self.from_user = type('obj', (object,), {'id': uid, 'username': username})()
            self.text = ""
            self.answer = callback.message.answer
            self.reply_markup = callback.message.reply_markup
    fake_msg = FakeMessage(user_id, callback.from_user.username or "")
    await profile_cmd(fake_msg)

@router.callback_query(F.data == "referral")
async def referral_cb(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    user = force_create_user(user_id, callback.from_user.username or "")
    if not user:
        return
    class FakeMessage:
        def __init__(self, uid, username):
            self.from_user = type('obj', (object,), {'id': uid, 'username': username})()
            self.text = ""
            self.answer = callback.message.answer
            self.reply_markup = callback.message.reply_markup
    fake_msg = FakeMessage(user_id, callback.from_user.username or "")
    await referral_cmd(fake_msg)

@router.callback_query(F.data == "premium")
async def premium_cb(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    await premium_cmd(callback.message)

@router.callback_query(F.data == "help")
async def help_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    await help_cmd(callback.message)
    await callback.answer()

@router.callback_query(F.data == "leaderboard")
async def leaderboard_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    await leaderboard_cmd(callback.message)
    await callback.answer()

@router.callback_query(F.data == "contact_admin")
async def contact_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    user_pages[user_id] = {"state": "waiting_contact"}
    await callback.message.edit_text("📩 Напишите сообщение админу.\n\n⏹ /cancel", reply_markup=main_menu())
    await callback.answer()

@router.callback_query(F.data == "promo_use")
async def promo_use_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    user_pages[user_id] = {"state": "waiting_promo_use"}
    await callback.message.edit_text(
        "🎁 **Введите промокод**\n\n"
        "Напиши код, чтобы активировать бонусы:\n\n"
        "⏹ /cancel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
    )
    await callback.answer()

@router.callback_query(F.data == "my_bonus")
async def my_bonus_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = force_create_user(user_id, callback.from_user.username or "")
    if not user:
        await callback.answer("❌ Ошибка!", show_alert=True)
        return
    b_img, b_req = get_bonus_balance(user_id)
    used, limit, prem, plan, bonus_img = get_image_stats(user_id)
    text = (
        f"📋 **Мои бонусы**\n\n"
        f"🎁 Бонусных картинок: {b_img}\n"
        f"📝 Бонусных запросов: {b_req}\n"
        f"🖼️ Картинок сегодня: {used}/{limit}\n"
        f"💎 План: {get_plan_emoji(user['plan'] if user['plan'] else 'basic')}"
    )
    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def back_main_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    await callback.message.edit_text("🤖 **Vertex AI**\n\n✏️ Просто напиши вопрос!", reply_markup=main_menu())
    await callback.answer()

# ========== ПЛАТЕЖИ ==========
@router.callback_query(F.data.startswith("pay_"))
async def pay_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    try:
        plan_type = callback.data.replace("pay_", "")
        plans = {
            "premium_1m": (49, 30, "premium", "💎 Premium 1 мес"),
            "premium_3m": (129, 90, "premium", "💎 Premium 3 мес"),
            "premium_6m": (249, 180, "premium", "💎 Premium 6 мес"),
            "premium_12m": (449, 365, "premium", "💎 Premium 12 мес"),
            "deluxe_1m": (99, 30, "premium_deluxe", "👑 Premium Deluxe 1 мес"),
            "deluxe_3m": (269, 90, "premium_deluxe", "👑 Premium Deluxe 3 мес"),
            "deluxe_6m": (499, 180, "premium_deluxe", "👑 Premium Deluxe 6 мес"),
            "deluxe_12m": (899, 365, "premium_deluxe", "👑 Premium Deluxe 12 мес"),
        }
        if plan_type not in plans:
            return await callback.answer("❌ Неверный тариф", show_alert=True)
        stars, days, plan, title = plans[plan_type]
        payload = secrets.token_hex(16)
        from database.db import get_db
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO payments (user_id, stars_amount, telegram_payload, status, timestamp, plan) VALUES (?, ?, ?, ?, ?, ?)",
                        (user_id, stars, payload, "pending", datetime.now().isoformat(), plan))
        await callback.bot.send_invoice(
            chat_id=user_id, title=title, description=f"{days} дней Premium",
            payload=payload, provider_token="", currency="XTR",
            prices=[LabeledPrice(label=title, amount=stars)], start_parameter="premium_sub"
        )
        await callback.answer()
    except Exception as e:
        await callback.answer("❌ Ошибка платежа", show_alert=True)

@router.pre_checkout_query()
async def pre_checkout(query: types.PreCheckoutQuery):
    await query.answer(ok=True)

@router.message(F.successful_payment)
async def payment_success(message: types.Message):
    payload = message.successful_payment.invoice_payload
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT stars_amount, plan FROM payments WHERE telegram_payload = ?", (payload,))
        row = cursor.fetchone()
    if row:
        stars, plan = row
        add_premium(message.from_user.id, 30, plan, paid=True)
        mark_paid_premium(message.from_user.id)
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE payments SET status = 'completed' WHERE telegram_payload = ?", (payload,))
        do_backup()
        plan_names = {'premium': '💎 Premium', 'premium_deluxe': '👑 Premium Deluxe'}
        await message.answer(f"✅ {plan_names.get(plan, 'Premium')} на 30 дней активирован!")
    else:
        await message.answer("❌ Ошибка активации")

# ========== АДМИН-CALLBACK'И ==========
@router.callback_query(F.data == "admin_panel")
async def admin_panel_cb(callback: types.CallbackQuery):
    if is_admin(callback.from_user.id):
        await callback.message.edit_text("🛡️ **АДМИН-ПАНЕЛЬ**", reply_markup=admin_kb())
        await callback.answer()
    else:
        await callback.answer("⛔ Нет доступа", show_alert=True)

@router.callback_query(F.data == "a_stats")
async def a_stats_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    total, prem, req, images, paid = get_stats()
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE plan = 'premium_deluxe' AND premium_until > datetime('now')")
        deluxe = cursor.fetchone()[0] or 0
    await callback.message.edit_text(
        f"📊 **СТАТИСТИКА**\n\n"
        f"👥 Всего: {total}\n"
        f"💎 Premium: {prem - deluxe}\n"
        f"👑 Premium Deluxe: {deluxe}\n"
        f"💰 Оплатили: {paid}\n"
        f"📝 Запросов: {req}\n"
        f"🖼️ Картинок: {images}",
        reply_markup=admin_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "a_chart")
async def a_chart_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    data = get_daily_stats(30)
    if not data:
        await callback.message.edit_text("📭 Нет данных.", reply_markup=admin_kb())
        await callback.answer()
        return
    dates = [d['date'] for d in data]
    new_users = [d['new_users'] for d in data]
    payments = [d['payments'] for d in data]
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(dates, new_users, label='Новые пользователи', color='blue', marker='o', linewidth=2, markersize=6)
    ax.plot(dates, payments, label='Оплаты Premium', color='green', marker='s', linewidth=2, markersize=6)
    ax.set_xlabel('Дата')
    ax.set_ylabel('Количество')
    ax.set_title('Новые пользователи и оплаты за 30 дней')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.tick_params(axis='x', rotation=45)
    ax.set_xticks([d for i, d in enumerate(dates) if i % 3 == 0])
    plt.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150)
    buf.seek(0)
    plt.close()
    await callback.message.delete()
    await callback.message.answer_photo(
        BufferedInputFile(file=buf.getvalue(), filename="chart.png"),
        caption="📈 Новые пользователи и оплаты за 30 дней",
        reply_markup=admin_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "a_users")
async def a_users_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, total_requests, image_requests, plan, is_blocked FROM users ORDER BY user_id LIMIT 20")
        users = cursor.fetchall()
    plan_emoji = {'basic': '🔴', 'premium': '💎', 'premium_deluxe': '👑'}
    if not users:
        text = "👥 Нет пользователей"
    else:
        text = "👥 **Пользователи**\n\n"
        for u in users:
            emoji = plan_emoji.get(u['plan'], '🔴')
            status_text = "⛔ Заблокирован" if u['is_blocked'] == 1 else "✅ Активен"
            name = u['username'] if u['username'] and u['username'] != str(u['user_id']) else "Без имени"
            text += f"{status_text} {emoji} **{name}** (ID: {u['user_id']})\n"
            text += f"   📝{u['total_requests']} | 🖼️{u['image_requests']}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    try:
        await callback.message.edit_text(text[:4000], reply_markup=kb)
    except:
        await callback.message.answer(text[:4000], reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "a_give_premium")
async def a_give_premium_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа", show_alert=True)
    try:
        from database.db import get_db
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, username, plan FROM users WHERE plan != 'premium' AND plan != 'premium_deluxe' LIMIT 20")
            users = cursor.fetchall()
        if not users:
            await callback.message.edit_text("👥 Все пользователи уже имеют Premium!", reply_markup=admin_kb())
            await callback.answer()
            return
        kb = InlineKeyboardMarkup(inline_keyboard=[])
        for u in users:
            user_id = u['user_id']
            name = u['username'] if u['username'] and u['username'] != str(u['user_id']) else str(user_id)
            plan = u['plan'] if u['plan'] else 'basic'
            kb.inline_keyboard.append([
                InlineKeyboardButton(text=f"👤 {name} ({plan})", callback_data=f"give_premium_{user_id}")
            ])
        kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])
        await callback.message.edit_text("💎 **Выдать Premium**\n\nВыберите пользователя:", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        print(f"❌ Ошибка a_give_premium: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)

@router.callback_query(F.data.startswith("give_premium_"))
async def give_premium_confirm(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    user_id = int(callback.data.replace("give_premium_", ""))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Premium", callback_data=f"confirm_premium_{user_id}_premium")],
        [InlineKeyboardButton(text="👑 Premium Deluxe", callback_data=f"confirm_premium_{user_id}_premium_deluxe")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="a_give_premium")]
    ])
    await callback.message.edit_text(f"👤 Пользователь: {user_id}\n\nВыберите план:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("confirm_premium_"))
async def confirm_premium(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа", show_alert=True)
    try:
        data = callback.data.split("_")
        user_id = int(data[2])
        plan = data[3]
        print(f"🔍 confirm_premium: user_id={user_id}, plan={plan}")
        if plan not in ['premium', 'premium_deluxe']:
            await callback.answer("❌ Неверный план", show_alert=True)
            return
        success = add_premium(user_id, 30, plan, paid=True)
        if success:
            plan_names = {'premium': '💎 Premium', 'premium_deluxe': '👑 Premium Deluxe'}
            user = get_user(user_id)
            if user:
                plan_actual = user['plan'] if 'plan' in user.keys() else 'unknown'
                until = user['premium_until'] if 'premium_until' in user.keys() else 'N/A'
                await callback.message.edit_text(
                    f"✅ {plan_names.get(plan, plan)} на 30 дней выдан {user_id}!\n"
                    f"📊 Текущий план: {plan_actual}\n"
                    f"📅 До: {until[:10] if until else 'бессрочно'}",
                    reply_markup=admin_kb()
                )
            else:
                await callback.message.edit_text(f"✅ {plan_names.get(plan, plan)} выдан {user_id}!", reply_markup=admin_kb())
            do_backup()
            await callback.answer("✅ Premium выдан!", show_alert=True)
        else:
            await callback.message.edit_text(f"❌ Ошибка выдачи Premium пользователю {user_id}", reply_markup=admin_kb())
            await callback.answer("❌ Ошибка!", show_alert=True)
    except Exception as e:
        print(f"❌ Ошибка confirm_premium: {e}")
        await callback.message.edit_text(f"❌ Ошибка: {str(e)}", reply_markup=admin_kb())
        await callback.answer("❌ Ошибка!", show_alert=True)

@router.callback_query(F.data == "a_change_plan")
async def a_change_plan_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, plan FROM users ORDER BY user_id LIMIT 20")
        users = cursor.fetchall()
    if not users:
        await callback.message.edit_text("👥 Нет пользователей", reply_markup=admin_kb())
        await callback.answer()
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for u in users:
        name = u['username'] if u['username'] and u['username'] != str(u['user_id']) else str(u['user_id'])
        current_plan = u['plan'] if u['plan'] else 'basic'
        emoji = {'basic': '🔴', 'premium': '💎', 'premium_deluxe': '👑'}.get(current_plan, '🔴')
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=f"{emoji} {name} ({current_plan})", callback_data=f"change_plan_{u['user_id']}")
        ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])
    await callback.message.edit_text("🔄 **Сменить тариф**\n\nВыберите пользователя:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("change_plan_"))
async def change_plan_select(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    user_id = int(callback.data.replace("change_plan_", ""))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Бесплатный", callback_data=f"set_plan_{user_id}_basic")],
        [InlineKeyboardButton(text="💎 Premium", callback_data=f"set_plan_{user_id}_premium")],
        [InlineKeyboardButton(text="👑 Premium Deluxe", callback_data=f"set_plan_{user_id}_premium_deluxe")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="a_change_plan")]
    ])
    await callback.message.edit_text(f"🔄 **Сменить тариф**\n\n👤 Пользователь: {user_id}\n\nВыберите новый план:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("set_plan_"))
async def set_plan_confirm(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    parts = callback.data.split("_")
    user_id = int(parts[2])
    new_plan = parts[3]
    success, msg = change_user_plan(user_id, new_plan)
    await callback.answer("✅" if success else "❌", show_alert=True)
    print(f"🔍 Смена плана: user_id={user_id}, new_plan={new_plan}, success={success}, msg={msg}")
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT plan, premium_until FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            print(f"🔍 План в БД: {row[0]}, premium_until: {row[1]}")
        else:
            print(f"❌ Пользователь {user_id} не найден!")
    user = get_user(user_id)
    if user:
        print(f"🔍 План из get_user: {user['plan']}")
    plan_names = {"basic": "🔴 Бесплатный", "premium": "💎 Premium", "premium_deluxe": "👑 Premium Deluxe"}
    await callback.message.edit_text(
        f"{msg}\n\n👤 Пользователь: {user_id}\n📊 Новый план: {plan_names.get(new_plan, new_plan.upper())}\n📅 Действует 30 дней",
        reply_markup=admin_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "a_messages")
async def a_messages_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_id, username, text, date, status FROM messages_to_admin ORDER BY date DESC LIMIT 20")
        messages = cursor.fetchall()
    if not messages:
        try:
            await callback.message.edit_text("📭 Нет обращений.", reply_markup=admin_kb())
        except:
            await callback.message.answer("📭 Нет обращений.", reply_markup=admin_kb())
        await callback.answer()
        return
    text = "📩 **Обращения**\n\n"
    for msg in messages:
        status = "🆕" if msg['status'] == "new" else "✅"
        name = msg['username'] if msg['username'] and msg['username'] != str(msg['user_id']) else str(msg['user_id'])
        text += f"{status} {msg['user_id']} — {name}\n"
        text += f"📝 {msg['text'][:50]}{'...' if len(msg['text']) > 50 else ''}\n"
        text += f"🕐 {msg['date'][:16]}\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Ответить", callback_data="reply_last")],
        [InlineKeyboardButton(text="🗑️ Очистить все", callback_data="delete_all_messages")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    try:
        await callback.message.edit_text(text[:4000], reply_markup=kb)
    except:
        await callback.message.answer(text[:4000], reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "reply_last")
async def reply_last_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM messages_to_admin WHERE status = 'new' ORDER BY date DESC LIMIT 1")
        row = cursor.fetchone()
    if not row:
        await callback.answer("❌ Нет новых обращений", show_alert=True)
        return
    msg_id = row[0]
    user_pages[callback.from_user.id] = {"state": "waiting_reply", "msg_id": msg_id}
    await callback.message.edit_text(
        "✏️ Введите текст ответа.\n\n⏹ /cancel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="a_messages")]
        ])
    )
    await callback.answer()

@router.callback_query(F.data == "delete_all_messages")
async def delete_all_messages_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages_to_admin")
    await callback.answer("🗑️ Все обращения удалены", show_alert=True)
    await a_messages_cb(callback)

@router.callback_query(F.data == "a_block")
async def a_block_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, is_blocked FROM users ORDER BY user_id LIMIT 20")
        users = cursor.fetchall()
    if not users:
        await callback.answer("❌ Нет пользователей", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for u in users:
        name = u['username'] if u['username'] and u['username'] != str(u['user_id']) else str(u['user_id'])
        status = "✅ Активен" if u['is_blocked'] == 0 else "⛔ Заблокирован"
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=f"{status} {name}", callback_data=f"block_user_{u['user_id']}")
        ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])
    await callback.message.edit_text("🚫 **Блокировка**\n\nНажмите на пользователя:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("block_user_"))
async def block_user_action(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    user_id = int(callback.data.replace("block_user_", ""))
    user = get_user(user_id)
    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    is_blocked = user['is_blocked'] if user['is_blocked'] else 0
    if is_blocked == 1:
        unblock_user(user_id)
        await callback.answer("✅ Пользователь разблокирован", show_alert=True)
    else:
        block_user(user_id)
        await callback.answer("⛔ Пользователь заблокирован", show_alert=True)
    do_backup()
    await a_block_cb(callback)

@router.callback_query(F.data == "a_plans")
async def a_plans_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    text = f"⚙️ **Тарифы**\n\n🔹 Бесплатный: {get_setting('image_limit_free')} карт\n💎 Premium: {get_setting('image_limit_premium')} карт\n👑 Premium Deluxe: {get_setting('image_limit_premium_deluxe')} карт"
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔹 Бесплатный", callback_data="edit_free"), InlineKeyboardButton(text="💎 Premium", callback_data="edit_premium")],
        [InlineKeyboardButton(text="👑 Premium Deluxe", callback_data="edit_deluxe")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ]))
    await callback.answer()

@router.callback_query(F.data.startswith("edit_"))
async def edit_plan_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    plan = callback.data.replace("edit_", "")
    plan_names = {'free': '🔹 Бесплатный', 'premium': '💎 Premium', 'deluxe': '👑 Premium Deluxe'}
    user_pages[callback.from_user.id] = {"state": "waiting_plan_edit", "plan": plan}
    await callback.message.edit_text(
        f"⚙️ {plan_names.get(plan)}\n\nВведите: <картинки>\nПример: 10\n\n⏹ /cancel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="a_plans")]])
    )
    await callback.answer()

@router.callback_query(F.data == "a_backup")
async def a_backup_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    await callback.message.edit_text("⏳ Бэкап...")
    result = GitHubBackup().backup_db()
    await callback.message.edit_text("✅ Бэкап создан!" if result else "❌ Ошибка", reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_broadcast")
async def a_broadcast_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    user_pages[callback.from_user.id] = {"state": "waiting_broadcast"}
    await callback.message.edit_text("📢 **Рассылка**\n\nВведите текст.\n\n⏹ /cancel", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]]))
    await callback.answer()

@router.callback_query(F.data == "a_email")
async def a_email_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 Входящие", callback_data="email_inbox")],
        [InlineKeyboardButton(text="📤 Написать", callback_data="email_send")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    await callback.message.edit_text("📧 **Почта**\n\nВыберите действие:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "email_inbox")
async def email_inbox_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, sender_id, sender_name, receiver_id, subject, text, date, is_read FROM emails WHERE receiver_id = ? OR receiver_id = 0 ORDER BY date DESC LIMIT 20", (callback.from_user.id,))
        emails = cursor.fetchall()
    if not emails:
        await callback.message.edit_text("📭 Нет писем.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="a_email")]]))
        await callback.answer()
        return
    text = "📩 **Входящие**\n\n"
    for e in emails:
        status = "📨" if e['is_read'] == 0 else "📖"
        name = e['sender_name'] if e['sender_name'] and e['sender_name'] != str(e['sender_id']) else str(e['sender_id'])
        text += f"{status} **{name}**\n"
        text += f"📝 {e['subject'][:30]}{'...' if len(e['subject']) > 30 else ''}\n"
        text += f"🕐 {e['date'][:16]}\n"
        text += f"`/email_read_{e['id']}`\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="email_inbox")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="a_email")]
    ])
    try:
        await callback.message.edit_text(text[:4000], reply_markup=kb)
    except:
        await callback.message.answer(text[:4000], reply_markup=kb)
    await callback.answer()

@router.message(Command("email_read"))
async def email_read_cmd(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ Нет доступа")
    try:
        parts = message.text.split() if message.text else []
        if len(parts) < 2:
            return await message.answer("❌ Использование: /email_read ID")
        email_id = int(parts[1])
        from database.db import get_db
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT sender_name, subject, text, date, receiver_id FROM emails WHERE id = ?", (email_id,))
            email = cursor.fetchone()
            if not email:
                return await message.answer("❌ Письмо не найдено")
            cursor.execute("UPDATE emails SET is_read = 1 WHERE id = ?", (email_id,))
        name = email['sender_name'] if email['sender_name'] and email['sender_name'] != str(email['sender_id']) else str(email['sender_id'])
        text = f"📩 **От:** {name}\n"
        text += f"📝 **Тема:** {email['subject']}\n"
        text += f"🕐 {email['date']}\n\n"
        text += f"{email['text']}"
        await message.answer(text, reply_markup=admin_kb())
    except:
        await message.answer("❌ Использование: /email_read ID")

@router.callback_query(F.data == "email_send")
async def email_send_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    user_pages[callback.from_user.id] = {"state": "waiting_email"}
    await callback.message.edit_text(
        "📧 **Новое письмо**\n\n"
        "Введите текст письма.\n"
        "Оно будет отправлено ВСЕМ админам.\n\n"
        "⏹ /cancel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="a_email")]])
    )
    await callback.answer()

# ========== ДОПОЛНИТЕЛЬНЫЕ АДМИН-ФУНКЦИИ ==========
# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ АДМИНКИ ==========
async def get_top_users():
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, total_requests, image_requests, plan FROM users ORDER BY total_requests DESC LIMIT 10")
        return cursor.fetchall()

async def use_promocode(code, user_id):
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, bonus_images, bonus_requests, max_uses, used FROM promocodes WHERE code = ? AND expires_at > datetime('now')", (code,))
        promo = cursor.fetchone()
        if not promo:
            return False, "❌ Промокод не найден или истёк"
        if promo['used'] >= promo['max_uses']:
            return False, "❌ Промокод уже использован"
        cursor.execute("SELECT id FROM promocode_uses WHERE promocode_id = ? AND user_id = ?", (promo['id'], user_id))
        if cursor.fetchone():
            return False, "❌ Вы уже использовали этот промокод"
        cursor.execute("INSERT INTO promocode_uses (promocode_id, user_id, used_at) VALUES (?, ?, ?)", 
                      (promo['id'], user_id, datetime.now().isoformat()))
        cursor.execute("UPDATE promocodes SET used = used + 1 WHERE id = ?", (promo['id'],))
        if promo['bonus_images'] > 0:
            cursor.execute("UPDATE users SET bonus_images = bonus_images + ? WHERE user_id = ?", (promo['bonus_images'], user_id))
        if promo['bonus_requests'] > 0:
            cursor.execute("UPDATE users SET bonus_requests = bonus_requests + ? WHERE user_id = ?", (promo['bonus_requests'], user_id))
        return True, f"✅ Промокод активирован! +{promo['bonus_images']} карт, +{promo['bonus_requests']} запросов"

async def log_admin_action(admin_id, action, target_id, details):
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO admin_log (admin_id, action, target_id, details, timestamp) VALUES (?, ?, ?, ?, ?)",
                      (admin_id, action, target_id, details, datetime.now().isoformat()))

async def get_promocodes():
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM promocodes ORDER BY created_at DESC")
        return cursor.fetchall()

@router.callback_query(F.data == "a_dashboard")
async def a_dashboard_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    total, prem, req, images, paid = get_stats()
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE date(joined) = date('now')")
        today = cursor.fetchone()[0] or 0
        cursor.execute("SELECT COUNT(*) FROM users WHERE date(joined) = date('now', '-1 day')")
        yesterday = cursor.fetchone()[0] or 0
        cursor.execute("SELECT COUNT(*) FROM payments WHERE date(timestamp) = date('now') AND status = 'completed'")
        today_payments = cursor.fetchone()[0] or 0
        cursor.execute("SELECT SUM(stars_amount) FROM payments WHERE status = 'completed'")
        total_revenue = cursor.fetchone()[0] or 0
    text = (
        f"📊 **ДАШБОРД**\n\n"
        f"👥 Всего: {total}\n"
        f"🆕 Сегодня: +{today}\n"
        f"📈 Вчера: {yesterday}\n"
        f"💎 Premium: {prem}\n"
        f"💰 Всего выручка: {total_revenue}⭐\n"
        f"💳 Оплат сегодня: {today_payments}\n"
        f"📝 Запросов: {req}\n"
        f"🖼️ Картинок: {images}\n"
    )
    await callback.message.edit_text(text, reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_finance")
async def a_finance_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(stars_amount) FROM payments WHERE status = 'completed'")
        total_revenue = cursor.fetchone()[0] or 0
        cursor.execute("SELECT SUM(stars_amount) FROM payments WHERE date(timestamp) = date('now') AND status = 'completed'")
        today_revenue = cursor.fetchone()[0] or 0
        cursor.execute("SELECT SUM(stars_amount) FROM payments WHERE date(timestamp) = date('now', '-7 days') AND status = 'completed'")
        week_revenue = cursor.fetchone()[0] or 0
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM payments WHERE status = 'completed'")
        payers = cursor.fetchone()[0] or 0
        cursor.execute("SELECT user_id, SUM(stars_amount) FROM payments WHERE status = 'completed' GROUP BY user_id ORDER BY SUM(stars_amount) DESC LIMIT 5")
        top = cursor.fetchall()
    text = (
        f"💰 **ФИНАНСЫ**\n\n"
        f"💵 Всего выручка: {total_revenue}⭐\n"
        f"📅 Сегодня: +{today_revenue}⭐\n"
        f"📆 За неделю: {week_revenue}⭐\n"
        f"👤 Платили: {payers} пользователей\n"
        f"📊 Средний чек: {round(total_revenue / payers, 1) if payers > 0 else 0}⭐\n\n"
        f"🏆 **Топ платящих:**\n"
    )
    for u in top:
        text += f"👤 {u['user_id']} — {u['SUM(stars_amount)']}⭐\n"
    await callback.message.edit_text(text, reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_top")
async def a_top_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    users = await get_top_users()
    if not users:
        await callback.message.edit_text("🏆 Нет данных", reply_markup=admin_kb())
        await callback.answer()
        return
    medals = ['🥇', '🥈', '🥉']
    text = "🏆 **Топ-10 активных пользователей**\n\n"
    for i, u in enumerate(users):
        medal = medals[i] if i < 3 else f"{i+1}."
        name = u['username'] or str(u['user_id'])
        plan_emoji = {"basic": "🔴", "premium": "💎", "premium_deluxe": "👑"}.get(u['plan'], "🔴")
        text += f"{medal} {plan_emoji} **{name}**\n"
        text += f"   📝 {u['total_requests']} запросов | 🖼️ {u['image_requests']} картинок\n\n"
    await callback.message.edit_text(text, reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_tags")
async def a_tags_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, plan, total_requests FROM users LIMIT 10")
        users = cursor.fetchall()
    text = "🏷️ **Управление тегами**\n\n"
    for u in users:
        tags = []
        if u['plan'] in ['premium', 'premium_deluxe']:
            tags.append("💎 VIP")
        if u['total_requests'] > 50:
            tags.append("🔥 Активен")
        else:
            tags.append("🆕 Новичок")
        text += f"👤 {u['username'] or u['user_id']}\n"
        text += f"   🏷️ {', '.join(tags)}\n\n"
    text += "\n`/tag add ID тег` — добавить тег\n`/tag remove ID тег` — удалить тег"
    await callback.message.edit_text(text, reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_segments")
async def a_segments_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE plan = 'premium' OR plan = 'premium_deluxe'")
        premium = cursor.fetchone()[0] or 0
        cursor.execute("SELECT COUNT(*) FROM users WHERE total_requests > 100")
        active = cursor.fetchone()[0] or 0
        cursor.execute("SELECT COUNT(*) FROM users WHERE date(joined) < date('now', '-30 days')")
        old = cursor.fetchone()[0] or 0
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 1")
        blocked = cursor.fetchone()[0] or 0
    text = (
        f"🎯 **СЕГМЕНТЫ ПОЛЬЗОВАТЕЛЕЙ**\n\n"
        f"💎 Premium: {premium}\n"
        f"🔥 Активные (>100 запросов): {active}\n"
        f"📅 Старые (>30 дней): {old}\n"
        f"🚫 Заблокированные: {blocked}\n"
    )
    await callback.message.edit_text(text, reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_promocodes")
async def a_promocodes_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать промокод", callback_data="promo_create")],
        [InlineKeyboardButton(text="📋 Список промокодов", callback_data="promo_list")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="promo_stats")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    await callback.message.edit_text("🎁 **Управление промокодами**", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "promo_create")
async def promo_create_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    user_pages[callback.from_user.id] = {"state": "waiting_promo"}
    await callback.message.edit_text(
        "🎁 **Создание промокода**\n\n"
        "Введите данные в формате:\n"
        "`код | картинки | запросы | макс_использований`\n\n"
        "Пример: `BONUS10 | 10 | 5 | 100`\n\n"
        "⏹ /cancel",
        reply_markup=admin_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "promo_list")
async def promo_list_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    promos = await get_promocodes()
    if not promos:
        await callback.message.edit_text("❌ Нет промокодов", reply_markup=admin_kb())
        await callback.answer()
        return
    text = "🎁 **Список промокодов**\n\n"
    for p in promos:
        text += f"📌 **{p['code']}**\n"
        text += f"   🎁 +{p['bonus_images']} карт, +{p['bonus_requests']} запросов\n"
        text += f"   📊 Использовано: {p['used']}/{p['max_uses']}\n"
        text += f"   🕐 До: {p['expires_at'][:10] if p['expires_at'] else '∞'}\n\n"
    await callback.message.edit_text(text[:4000], reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "promo_stats")
async def promo_stats_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM promocodes")
        total = cursor.fetchone()[0] or 0
        cursor.execute("SELECT SUM(used) FROM promocodes")
        used_total = cursor.fetchone()[0] or 0
        cursor.execute("SELECT COUNT(*) FROM promocode_uses WHERE date(used_at) = date('now')")
        today_used = cursor.fetchone()[0] or 0
    text = (
        f"📊 **Статистика промокодов**\n\n"
        f"📌 Всего создано: {total}\n"
        f"✅ Всего использовано: {used_total}\n"
        f"📅 Использовано сегодня: {today_used}\n"
        f"📈 Конверсия: {round(used_total / max(total, 1) * 100, 1)}%\n"
    )
    await callback.message.edit_text(text, reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_bonus")
async def a_bonus_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    user_pages[callback.from_user.id] = {"state": "waiting_bonus"}
    await callback.message.edit_text(
        "⭐ **Начисление бонусов**\n\n"
        "Введите данные в формате:\n"
        "`ID пользователя | картинки | запросы`\n\n"
        "Пример: `123456789 | 10 | 5`\n\n"
        "⏹ /cancel",
        reply_markup=admin_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "a_chat")
async def a_chat_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    await callback.message.edit_text(
        "💬 **Чат с пользователями**\n\n"
        "Выберите пользователя для чата:\n"
        "`/chat ID` — начать диалог с пользователем\n"
        "`/chat list` — список активных чатов",
        reply_markup=admin_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "a_autopilot")
async def a_autopilot_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    text = (
        "🤖 **AI-АВТОПИЛОТ**\n\n"
        "Автоматические сценарии:\n\n"
        "1️⃣ Новый пользователь → приветствие через 1 час\n"
        "2️⃣ 3 дня не заходил → напоминание с бонусом\n"
        "3️⃣ 5 запросов сделал → предложение Premium\n"
        "4️⃣ 7 дней подряд → бонус удваивается\n"
        "5️⃣ Не купил Premium за 30 дней → скидка 20%\n\n"
        "🟢 Автопилот активен (5 сценариев)\n"
        "`/autopilot config` — настройка сценариев"
    )
    await callback.message.edit_text(text, reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_automation")
async def a_automation_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать сценарий", callback_data="auto_create")],
        [InlineKeyboardButton(text="📋 Список сценариев", callback_data="auto_list")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="auto_stats")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    await callback.message.edit_text("🔁 **Автоматические сценарии**\n\nУправление автоворонками:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "a_design")
async def a_design_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎨 Тёмная тема", callback_data="design_dark")],
        [InlineKeyboardButton(text="☀️ Светлая тема", callback_data="design_light")],
        [InlineKeyboardButton(text="💎 Premium стиль", callback_data="design_premium")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    await callback.message.edit_text("🎨 **Настройка дизайна**\n\nВыберите тему оформления бота:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "a_files")
async def a_files_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    text = "📁 **Файловое хранилище**\n\n"
    text += "📄 Всего файлов: 0\n"
    text += "📊 Занято: 0 МБ\n"
    text += "📤 Загружено сегодня: 0\n\n"
    text += "`/files list` — список файлов\n"
    text += "`/files clean` — очистить хранилище"
    await callback.message.edit_text(text, reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_notifications")
async def a_notifications_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔔 Включить все", callback_data="notif_on")],
        [InlineKeyboardButton(text="🔕 Выключить все", callback_data="notif_off")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="notif_settings")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    await callback.message.edit_text("🔔 **Уведомления**\n\nНастройка автоматических уведомлений:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "a_export")
async def a_export_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, joined, plan, premium_until, total_requests, image_requests, is_blocked FROM users")
        users = cursor.fetchall()
    if not users:
        await callback.message.edit_text("❌ Нет данных", reply_markup=admin_kb())
        await callback.answer()
        return
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Имя', 'Дата регистрации', 'План', 'Premium до', 'Запросы', 'Картинки', 'Заблокирован'])
    for u in users:
        writer.writerow([u['user_id'], u['username'], u['joined'], u['plan'], u['premium_until'], u['total_requests'], u['image_requests'], u['is_blocked']])
    csv_data = output.getvalue()
    await callback.message.delete()
    await callback.message.answer_document(
        BufferedInputFile(file=csv_data.encode('utf-8'), filename="users_export.csv"),
        caption="📊 Экспорт пользователей",
        reply_markup=admin_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "a_log")
async def a_log_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT admin_id, action, target_id, details, timestamp FROM admin_log ORDER BY timestamp DESC LIMIT 20")
        logs = cursor.fetchall()
    if not logs:
        await callback.message.edit_text("📋 Журнал пуст", reply_markup=admin_kb())
        await callback.answer()
        return
    text = "📋 **Журнал действий**\n\n"
    for log in logs:
        text += f"🕐 {log['timestamp'][:16]}\n"
        text += f"👤 Админ: {log['admin_id']}\n"
        text += f"📌 {log['action']}"
        if log['target_id']:
            text += f" → {log['target_id']}"
        if log['details']:
            text += f" ({log['details']})"
        text += "\n\n"
    await callback.message.edit_text(text[:4000], reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_web")
async def a_web_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    text = (
        "🌐 **ВЕБ-КАБИНЕТ**\n\n"
        "Открой в браузере:\n"
        "🔗 https://tg-bot-qinm.onrender.com/admin\n\n"
        "📊 Доступно:\n"
        "• Дашборд с графиками\n"
        "• Управление пользователями\n"
        "• Финансовая аналитика\n"
        "• Настройка сценариев\n\n"
        "🔑 Для входа используй:\n"
        f"🆔 ID: {callback.from_user.id}\n"
        "🔐 Код: 30121979"
    )
    try:
        await callback.message.edit_text(text, reply_markup=admin_kb())
    except:
        await callback.message.answer(text, reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_mobile")
async def a_mobile_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    text = (
        "📱 **МОБИЛЬНАЯ ВЕРСИЯ**\n\n"
        "Открой в мобильном браузере:\n"
        "🔗 https://tg-bot-qinm.onrender.com/mobile\n\n"
        "📱 Оптимизировано для телефонов\n"
        "📊 Управление в один клик\n"
        "⚡ Быстрый доступ к статистике"
    )
    try:
        await callback.message.edit_text(text, reply_markup=admin_kb())
    except:
        await callback.message.answer(text, reply_markup=admin_kb())
    await callback.answer()

# ========== ОБРАБОТЧИК ВВОДА АДМИНА ==========
async def handle_admin_input(message: types.Message):
    user_id = message.from_user.id
    state = user_pages.get(user_id, {})
    if message.text == "/cancel":
        user_pages.pop(user_id, None)
        await message.answer("✅ Отменено", reply_markup=main_menu() if not is_admin(user_id) else admin_kb())
        return
    
    if state.get("state") == "waiting_promo":
        try:
            parts = [p.strip() for p in message.text.split('|')]
            if len(parts) < 4:
                await message.answer("❌ Неверный формат! Нужно: код | картинки | запросы | макс_использований")
                return
            code = parts[0].upper()
            bonus_images = int(parts[1])
            bonus_requests = int(parts[2])
            max_uses = int(parts[3])
            from database.db import get_db
            with get_db() as conn:
                cursor = conn.cursor()
                expires_at = (datetime.now() + timedelta(days=30)).isoformat()
                cursor.execute("INSERT INTO promocodes (code, bonus_images, bonus_requests, max_uses, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
                              (code, bonus_images, bonus_requests, max_uses, datetime.now().isoformat(), expires_at))
            await message.answer(f"✅ Промокод **{code}** создан!", reply_markup=admin_kb())
            await log_admin_action(user_id, "create_promo", None, f"{code} +{bonus_images}img +{bonus_requests}req")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}", reply_markup=admin_kb())
        user_pages.pop(user_id, None)
        return
    
    if state.get("state") == "waiting_bonus":
        try:
            parts = [p.strip() for p in message.text.split('|')]
            if len(parts) < 3:
                await message.answer("❌ Неверный формат! Нужно: ID | картинки | запросы")
                return
            target_id = int(parts[0])
            bonus_images = int(parts[1])
            bonus_requests = int(parts[2])
            from database.db import get_db
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET bonus_images = bonus_images + ?, bonus_requests = bonus_requests + ? WHERE user_id = ?",
                             (bonus_images, bonus_requests, target_id))
            await message.answer(f"✅ Начислено: +{bonus_images} карт, +{bonus_requests} запросов пользователю {target_id}", reply_markup=admin_kb())
            await log_admin_action(user_id, "add_bonus", target_id, f"+{bonus_images}img +{bonus_requests}req")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}", reply_markup=admin_kb())
        user_pages.pop(user_id, None)
        return
    
    if state.get("state") == "waiting_reply":
        msg_id = state.get("msg_id")
        reply_text = message.text
        from database.db import get_db
        with get_db() as conn:
            cursor = conn.cursor()
            msg = get_message_by_id(msg_id)
            if msg:
                user_id_target = msg['user_id']
                cursor.execute("UPDATE messages_to_admin SET status = 'answered' WHERE id = ?", (msg_id,))
                try:
                    await message.bot.send_message(user_id_target, f"📩 **Ответ:**\n\n{reply_text}")
                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_msg_{msg_id}")],
                        [InlineKeyboardButton(text="🔙 Назад", callback_data="a_messages")]
                    ])
                    await message.answer(f"✅ Ответ отправлен {user_id_target}", reply_markup=kb)
                except Exception as e:
                    await message.answer(f"❌ Ошибка: {e}", reply_markup=admin_kb())
            else:
                await message.answer("❌ Сообщение не найдено", reply_markup=admin_kb())
        user_pages.pop(user_id, None)
        return
    
    if state.get("state") == "waiting_plan_edit":
        try:
            parts = message.text.split() if message.text else []
            if len(parts) != 1:
                return await message.answer("❌ Формат: число картинок", reply_markup=admin_kb())
            images = int(parts[0])
            plan = state.get("plan")
            if plan == 'free':
                set_setting('image_limit_free', str(images))
            elif plan == 'premium':
                set_setting('image_limit_premium', str(images))
            elif plan == 'deluxe':
                set_setting('image_limit_premium_deluxe', str(images))
            await message.answer(f"✅ Обновлено: {images} картинок", reply_markup=admin_kb())
            do_backup()
            user_pages.pop(user_id, None)
        except:
            await message.answer("❌ Ошибка! Введите число", reply_markup=admin_kb())
        return
    
    if state.get("state") == "waiting_broadcast":
        if not message.text or not message.text.strip():
            await message.answer("❌ Текст рассылки не может быть пустым!", reply_markup=admin_kb())
            user_pages.pop(user_id, None)
            return
        await message.answer("📢 Рассылка...")
        from database.db import get_db
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE is_blocked = 0")
            users = cursor.fetchall()
        sent = 0
        for u in users:
            try:
                await message.bot.send_message(u['user_id'], f"📢 {message.text}")
                sent += 1
                await asyncio.sleep(0.05)
            except:
                pass
        await message.answer(f"✅ Отправлено: {sent}", reply_markup=admin_kb())
        do_backup()
        user_pages.pop(user_id, None)
        return
    
    if state.get("state") == "waiting_contact":
        from database.db import get_db
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO messages_to_admin (user_id, username, text, date) VALUES (?, ?, ?, ?)",
                        (user_id, message.from_user.username or "", message.text, datetime.now().isoformat()))
        await message.bot.send_message(int(os.getenv('ADMIN_ID', 6957852385)), f"📩 От {user_id}:\n{message.text}")
        await message.answer("✅ Отправлено!", reply_markup=main_menu())
        user_pages.pop(user_id, None)
        return
    
    if state.get("state") == "waiting_email":
        from database.db import get_db
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM admins")
            admins = cursor.fetchall()
        sent = 0
        for admin in admins:
            try:
                await message.bot.send_message(admin['user_id'], f"📧 **Письмо от админа**\n\n{message.text}")
                sent += 1
                await asyncio.sleep(0.05)
            except:
                pass
        await message.answer(f"✅ Письмо отправлено {sent} админам!", reply_markup=admin_kb())
        user_pages.pop(user_id, None)
        return

