from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, BufferedInputFile
from database.db import *
from ai.client import solve_problem
from backup import GitHubBackup
import logging, secrets, os, requests, asyncio
from datetime import datetime

router = Router()
logger = logging.getLogger(__name__)
user_modes = {}
user_pages = {}
ADMIN_CODE = "30121979"
API_KEY = os.getenv('OPENAI_API_KEY')
IMAGE_MODEL = "flux-schnell"
PROMPT_MODEL = "gpt-4.1-nano"

def force_create_user(user_id, username=None):
    try:
        user = get_user(user_id)
        if user:
            if len(user) > 9 and user[9] == 'basic' and user[3] and user[3] > datetime.now().isoformat():
                from database.db import get_db
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE users SET plan = 'premium' WHERE user_id = ?", (user_id,))
                    logger.info(f"🔥 Исправлен план для {user_id} на premium")
                user = get_user(user_id)
            return user
        logger.info(f"👤 Создаём пользователя {user_id}")
        result = create_user(user_id, username or str(user_id))
        if result:
            user = get_user(user_id)
            if user:
                logger.info(f"✅ Пользователь {user_id} создан")
                return user
        logger.error(f"❌ НЕ УДАЛОСЬ создать {user_id}")
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка force_create_user: {e}")
        return None

def do_backup():
    try:
        GitHubBackup().backup_db()
    except:
        pass

def get_plan_emoji(plan):
    if plan == 'premium_deluxe':
        return "👑 Premium Deluxe ✨✨✨"
    elif plan == 'premium':
        return "💎 Premium ✨"
    else:
        return "🔴 Бесплатный"

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧠 Текст", callback_data="mode_text"), InlineKeyboardButton(text="🖼️ Картинка", callback_data="mode_image")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"), InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="👥 Рефералы", callback_data="referral"), InlineKeyboardButton(text="💎 Premium", callback_data="premium")],
        [InlineKeyboardButton(text="📩 Админу", callback_data="contact_admin"), InlineKeyboardButton(text="❓ Помощь", callback_data="help")],
        [InlineKeyboardButton(text="🏆 Рейтинг", callback_data="leaderboard"), InlineKeyboardButton(text="🛡️ Админ", callback_data="admin_panel")]
    ])

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="a_stats"), InlineKeyboardButton(text="👥 Пользователи", callback_data="a_users")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="a_broadcast"), InlineKeyboardButton(text="💎 Выдать Premium", callback_data="a_give_premium")],
        [InlineKeyboardButton(text="⚙️ Тарифы", callback_data="a_plans"), InlineKeyboardButton(text="🚫 Блокировка", callback_data="a_block")],
        [InlineKeyboardButton(text="💾 Бэкап", callback_data="a_backup"), InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

# ========== КОМАНДЫ ==========

@router.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    user = force_create_user(user_id, username)
    if not user:
        await message.answer("❌ Ошибка регистрации. Попробуйте позже.")
        return
    
    args = message.text.split()
    if len(args) > 1 and args[1].isdigit() and int(args[1]) != user_id:
        add_referral(int(args[1]), user_id)
        await message.answer("👤 Вы приглашены! Реферер +5 запросов.")
    
    await message.answer(
        "🤖 Vertex AI\n\n🧠 ИИ в Telegram!\n✅ 10 запросов/день\n💎 Premium: безлимит\n👥 Приведи друга → +5 запросов\n\nПросто напиши вопрос!",
        reply_markup=main_menu()
    )

# ========== КРАСИВЫЙ ПРОФИЛЬ ==========

@router.message(Command("profile"))
async def profile_cmd(message: types.Message):
    user_id = message.from_user.id
    user = force_create_user(user_id, message.from_user.username or "")
    if not user:
        await message.answer("❌ Ошибка! Попробуйте позже.", reply_markup=main_menu())
        return
    
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
        refs = cursor.fetchone()[0] or 0
    
    used, limit, prem, plan = get_image_stats(user_id)
    total_requests = user[5] if len(user) > 5 and user[5] else 0
    total_images = user[8] if len(user) > 8 and user[8] else 0
    
    plan_emoji = get_plan_emoji(plan)
    remaining = limit - used
    
    text = f"👤 **ПРОФИЛЬ**\n\n"
    text += f"🆔 {user[0]}\n"
    text += f"📆 Регистрация: {user[2][:10] if user[2] else 'Нет'}\n"
    text += f"👥 Рефералов: {refs}\n"
    text += f"📊 Всего запросов: {total_requests}\n"
    text += f"🖼️ Всего картинок: {total_images}\n"
    text += f"🖼️ Картинок сегодня: {used}/{limit} (осталось {remaining})\n"
    text += f"💎 План: {plan_emoji}"
    
    await message.answer(text, reply_markup=main_menu())

# ========== КРАСИВАЯ СТАТИСТИКА ==========

@router.message(Command("stats"))
async def stats_cmd(message: types.Message):
    user_id = message.from_user.id
    user = force_create_user(user_id, message.from_user.username or "")
    if not user:
        await message.answer("❌ Ошибка! Попробуйте позже.", reply_markup=main_menu())
        return
    
    ok, rem = can_request(user_id)
    used, limit, prem, plan = get_image_stats(user_id)
    trial = get_trial_remaining(user_id)
    
    total_requests = user[5] if len(user) > 5 and user[5] else 0
    total_images = user[8] if len(user) > 8 and user[8] else 0
    
    plan_emoji = get_plan_emoji(plan)
    remaining = limit - used
    
    text = f"📊 **СТАТИСТИКА**\n\n"
    
    if prem:
        text += f"📝 Текстовые запросы: ♾️ Безлимит\n"
    else:
        text += f"📝 Осталось запросов: {rem} из 10\n"
    
    text += f"🖼️ Картинок сегодня: {used}/{limit} (осталось {remaining})\n"
    
    if trial > 0 and not prem:
        text += f"🎁 Пробный период: {trial} картинок\n"
    
    text += f"📊 Всего запросов: {total_requests}\n"
    text += f"🖼️ Всего картинок: {total_images}\n"
    text += f"💎 План: {plan_emoji}"
    
    await message.answer(text, reply_markup=main_menu())

@router.message(Command("subscribe"))
async def subscribe_cmd(message: types.Message):
    user_id = message.from_user.id
    force_create_user(user_id, message.from_user.username or "")
    
    text = (
        "💎 Выберите тариф Premium\n\n"
        "📋 Сравнение тарифов:\n\n"
        "🔴 Бесплатный — 0⭐\n"
        "• 10 текстовых запросов/день\n"
        "• 3 картинки/день\n"
        "• Обычная обработка\n\n"
        "💎 Premium — 49⭐/мес\n"
        "• Безлимит текстовых запросов\n"
        "• 50 картинок/день\n"
        "• Приоритетная обработка\n"
        "• ✨ Бонус: +5 реферальных запросов\n\n"
        "👑 Premium Deluxe — 99⭐/мес\n"
        "• Безлимит текстовых запросов\n"
        "• 200 картинок/день\n"
        "• Приоритетная обработка\n"
        "• Эксклюзивные промпты\n"
        "• VIP-поддержка 24/7\n"
        "• ✨✨ Бонус: +20 реферальных запросов"
    )
    
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Premium 49⭐", callback_data="pay_premium"), InlineKeyboardButton(text="👑 Deluxe 99⭐", callback_data="pay_deluxe")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
    )

@router.message(Command("referral"))
async def referral_cmd(message: types.Message):
    user_id = message.from_user.id
    user = force_create_user(user_id, message.from_user.username or "")
    if not user:
        await message.answer("❌ Ошибка! Попробуйте позже.", reply_markup=main_menu())
        return
    
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
        count = cursor.fetchone()[0] or 0
    
    link = f"https://t.me/Vertex1bot?start={user_id}"
    
    plan = get_user_plan(user_id)
    if plan == 'premium_deluxe':
        bonus = "20"
    else:
        bonus = "5"
    
    await message.answer(
        f"👥 **Рефералы**\n\n"
        f"👤 Приглашено: {count}\n"
        f"💰 Бонус: +{bonus} запросов за каждого друга\n\n"
        f"🔗 Твоя ссылка:\n{link}\n\n"
        f"📤 Отправь ссылку друзьям и получай бонусы!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться", url=f"https://t.me/share/url?url={link}&text=🤖 Присоединяйся к Vertex AI!")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
    )

@router.message(Command("help"))
async def help_cmd(message: types.Message):
    force_create_user(message.from_user.id, message.from_user.username or "")
    text = "❓ Помощь\n\n/start — меню\n/profile — профиль\n/stats — статистика\n/subscribe — Premium\n/referral — рефералы"
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
        return await message.answer("🏆 Пока нет данных", reply_markup=main_menu())
    
    medals = ['🥇', '🥈', '🥉']
    text = "🏆 **Рейтинг**\n\n"
    for i, u in enumerate(users):
        medal = medals[i] if i < 3 else f"{i+1}."
        name = u[1] or str(u[0])
        text += f"{medal} {name} — {u[2]} задач\n"
    
    await message.answer(text, reply_markup=main_menu())

@router.message(Command("contact_admin"))
async def contact_admin_cmd(message: types.Message):
    user_id = message.from_user.id
    force_create_user(user_id, message.from_user.username or "")
    user_pages[user_id] = {"state": "waiting_contact"}
    await message.answer("📩 Напишите сообщение админу.\n⏹ /cancel", reply_markup=main_menu())

# ========== ОБРАБОТКА ТЕКСТА ==========

@router.message(F.text)
async def handle_message(message: types.Message):
    if message.text.startswith("/"):
        return
    user_id = message.from_user.id
    state = user_pages.get(user_id, {})
    
    if state.get("state") in ["waiting_plan_edit", "waiting_premium_user", "waiting_broadcast", "waiting_block_user", "waiting_contact"]:
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
    ok, rem = can_request(user_id)
    if not ok:
        return await message.answer("🔒 Лимит исчерпан! Купи Premium: /subscribe")
    prem = is_premium(user_id)
    status_msg = await message.answer("🤔 Думаю...")
    try:
        answer = solve_problem(message.text, "chat", prem)
        add_request(user_id)
        do_backup()
        await status_msg.edit_text(f"🧠 {answer}\n\n{'♾️ Безлимит' if prem else f'Осталось {rem-1} запросов'}")
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def generate_image(message: types.Message):
    user_id = message.from_user.id
    logger.info(f"🎨 Генерация картинки для {user_id}")
    
    if not API_KEY:
        return await message.answer("❌ API ключ не настроен")
    
    trial_rem = get_trial_remaining(user_id)
    used, limit, prem, plan = get_image_stats(user_id)
    logger.info(f"📊 До генерации: used={used}, limit={limit}")
    
    if prem:
        can_gen = used < limit
    elif trial_rem > 0:
        can_gen = True
        limit = 5
    else:
        can_gen, _ = can_generate_image(user_id)
    
    if not can_gen:
        return await message.answer(f"❌ Лимит картинок исчерпан! {used}/{limit}\n💎 Купи Premium: /subscribe")
    
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
        
        for p in [10, 25, 45, 60, 75, 90]:
            await asyncio.sleep(0.2)
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
                        logger.info(f"🎁 Пробная картинка для {user_id}")
                    else:
                        add_image_request(user_id)
                        logger.info(f"📸 +1 картинка для {user_id}")
                    
                    do_backup()
                    
                    new_used, new_limit, new_prem, new_plan = get_image_stats(user_id)
                    logger.info(f"📊 После генерации: used={new_used}, limit={new_limit}")
                    
                    plan_emoji = get_plan_emoji(new_plan)
                    remaining = new_limit - new_used
                    
                    await message.answer_photo(
                        BufferedInputFile(file=img_data.content, filename="image.webp"),
                        caption=f"🖼️ **Твоя картинка**\n📝 {user_prompt[:50]}...\n\n📊 Осталось картинок: {remaining}\n💎 План: {plan_emoji}"
                    )
                    await status_msg.delete()
                    return
        
        await status_msg.edit_text("❌ Не удалось получить картинку")
    except Exception as e:
        logger.error(f"❌ Ошибка генерации: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

# ========== CALLBACK'и ==========

@router.callback_query(F.data.in_(["mode_text", "mode_image"]))
async def set_mode(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = force_create_user(user_id, callback.from_user.username or "")
    if not user:
        await callback.answer("❌ Ошибка!", show_alert=True)
        return
    mode = callback.data.replace("mode_", "")
    user_modes[user_id] = mode
    await callback.answer(f"✅ Режим: {'🧠 Текст' if mode == 'text' else '🖼️ Картинка'}", show_alert=True)
    await callback.message.edit_text(f"{'🧠 Текст' if mode == 'text' else '🖼️ Картинка'}\n\nГотов к работе!", reply_markup=main_menu())

@router.callback_query(F.data == "stats")
async def stats_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = force_create_user(user_id, callback.from_user.username or "")
    if not user:
        await callback.answer("❌ Ошибка!", show_alert=True)
        return
    await stats_cmd(callback.message)
    await callback.answer()

@router.callback_query(F.data == "profile")
async def profile_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = force_create_user(user_id, callback.from_user.username or "")
    if not user:
        await callback.answer("❌ Ошибка!", show_alert=True)
        return
    await profile_cmd(callback.message)
    await callback.answer()

@router.callback_query(F.data == "referral")
async def referral_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = force_create_user(user_id, callback.from_user.username or "")
    if not user:
        await callback.answer("❌ Ошибка!", show_alert=True)
        return
    await referral_cmd(callback.message)
    await callback.answer()

@router.callback_query(F.data == "premium")
async def premium_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    await subscribe_cmd(callback.message)
    await callback.answer()

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
    await callback.message.edit_text("📩 Напишите сообщение админу.\n⏹ /cancel", reply_markup=main_menu())
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def back_main_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    await start_cmd(callback.message)
    await callback.answer()

@router.callback_query(F.data.startswith("pay_"))
async def pay_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    try:
        plan_type = callback.data.replace("pay_", "")
        if plan_type == "premium":
            stars, days, plan = 49, 30, "premium"
            title = "Premium 1 мес"
        elif plan_type == "deluxe":
            stars, days, plan = 99, 30, "premium_deluxe"
            title = "Premium Deluxe 1 мес"
        else:
            return await callback.answer("❌ Неверный тариф", show_alert=True)
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
        add_premium(message.from_user.id, 30, plan)
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE payments SET status = 'completed' WHERE telegram_payload = ?", (payload,))
        do_backup()
        plan_names = {'premium': '💎 Premium', 'premium_deluxe': '👑 Premium Deluxe'}
        await message.answer(f"✅ {plan_names.get(plan, 'Premium')} на 30 дней активирован!")
    else:
        await message.answer("❌ Ошибка активации")

# ========== АДМИНКА ==========

@router.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if is_admin(message.from_user.id):
        await message.answer("🛡️ АДМИН-ПАНЕЛЬ", reply_markup=admin_kb())
    else:
        await message.answer("🔐 Введите код: /admin_code 30121979")

@router.message(Command("admin_code"))
async def admin_code_cmd(message: types.Message):
    if len(message.text.split()) > 1 and message.text.split()[1] == ADMIN_CODE:
        add_admin(message.from_user.id)
        await message.answer("✅ Вы админ!", reply_markup=admin_kb())

@router.callback_query(F.data == "admin_panel")
async def admin_panel_cb(callback: types.CallbackQuery):
    if is_admin(callback.from_user.id):
        await callback.message.edit_text("🛡️ АДМИН-ПАНЕЛЬ", reply_markup=admin_kb())
        await callback.answer()
    else:
        await callback.answer("⛔ Нет доступа", show_alert=True)

# ========== АДМИНКА: СТАТИСТИКА ==========

@router.callback_query(F.data == "a_stats")
async def a_stats_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    total, prem, req, images = get_stats()
    
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE plan = 'premium_deluxe' AND premium_until > datetime('now')")
        deluxe = cursor.fetchone()[0] or 0
    
    await callback.message.edit_text(
        f"📊 **СТАТИСТИКА БОТА**\n\n"
        f"👥 Всего пользователей: {total}\n"
        f"💎 Premium: {prem - deluxe}\n"
        f"👑 Premium Deluxe: {deluxe}\n"
        f"📝 Всего запросов: {req}\n"
        f"🖼️ Всего картинок: {images}",
        reply_markup=admin_kb()
    )
    await callback.answer()

# ========== АДМИНКА: ПОЛЬЗОВАТЕЛИ ==========

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
        text = "👥 Пользователей не найдено"
    else:
        text = "👥 **Пользователи**\n\n"
        for u in users:
            emoji = plan_emoji.get(u[4], '🔴')
            blocked = "🚫" if u[5] == 1 else "✅"
            text += f"{blocked} {emoji} {u[0]} — {u[1] or 'без имени'}\n"
            text += f"   📝{u[2]} запросов | 🖼️{u[3]} картинок\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

# ========== АДМИНКА: ВЫДАТЬ PREMIUM ==========

@router.callback_query(F.data == "a_give_premium")
async def a_give_premium_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, plan FROM users WHERE plan = 'basic' ORDER BY user_id LIMIT 20")
        users = cursor.fetchall()
    
    if not users:
        await callback.message.edit_text("👥 Все пользователи уже имеют Premium!", reply_markup=admin_kb())
        await callback.answer()
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for u in users:
        username = u[1] or str(u[0])
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=f"👤 {username}", callback_data=f"give_premium_{u[0]}")
        ])
    
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])
    
    await callback.message.edit_text(
        "💎 **Выдать Premium**\n\nВыберите пользователя для выдачи Premium (30 дней):",
        reply_markup=kb
    )
    await callback.answer()

@router.callback_query(F.data.startswith("give_premium_"))
async def give_premium_confirm(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    user_id = int(callback.data.replace("give_premium_", ""))
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Premium (30 дней)", callback_data=f"confirm_premium_{user_id}_premium")],
        [InlineKeyboardButton(text="👑 Premium Deluxe (30 дней)", callback_data=f"confirm_premium_{user_id}_premium_deluxe")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="a_give_premium")]
    ])
    
    await callback.message.edit_text(
        f"👤 Пользователь: {user_id}\n\nВыберите план:",
        reply_markup=kb
    )
    await callback.answer()

@router.callback_query(F.data.startswith("confirm_premium_"))
async def confirm_premium(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    parts = callback.data.split("_")
    user_id = int(parts[2])
    plan = parts[3]
    
    add_premium(user_id, 30, plan)
    do_backup()
    
    plan_names = {'premium': '💎 Premium', 'premium_deluxe': '👑 Premium Deluxe'}
    
    await callback.message.edit_text(
        f"✅ {plan_names.get(plan, 'Premium')} на 30 дней выдан пользователю {user_id}!",
        reply_markup=admin_kb()
    )
    await callback.answer()

# ========== АДМИНКА: БЛОКИРОВКА ==========

@router.callback_query(F.data == "a_block")
async def a_block_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, is_blocked FROM users ORDER BY user_id LIMIT 20")
        users = cursor.fetchall()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for u in users:
        username = u[1] or str(u[0])
        status = "🔓" if u[2] == 0 else "🔒"
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=f"{status} {username}", callback_data=f"block_user_{u[0]}")
        ])
    
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])
    
    await callback.message.edit_text(
        "🚫 **Блокировка пользователей**\n\nНажмите на пользователя для блокировки/разблокировки:",
        reply_markup=kb
    )
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
    
    is_blocked = user[6] if len(user) > 6 else 0
    
    if is_blocked == 1:
        unblock_user(user_id)
        await callback.answer("✅ Пользователь РАЗБЛОКИРОВАН", show_alert=True)
    else:
        block_user(user_id)
        await callback.answer("🚫 Пользователь ЗАБЛОКИРОВАН", show_alert=True)
    
    do_backup()
    await a_block_cb(callback)

# ========== АДМИНКА: ТАРИФЫ ==========

@router.callback_query(F.data == "a_plans")
async def a_plans_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    text = f"⚙️ **Тарифы**\n\n🔹 Бесплатный: {get_setting('image_limit_free')} карт, {get_setting('free_input_chars')} симв\n💎 Premium: {get_setting('image_limit_premium')} карт, {get_setting('premium_input_chars')} симв\n👑 Premium Deluxe: {get_setting('image_limit_premium_deluxe')} карт, {get_setting('premium_deluxe_input_chars')} симв"
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
        f"⚙️ **{plan_names.get(plan)}**\n\nВведите: `<картинки> <символы>`\nПример: `10 1000`\n\n⏹ /cancel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="a_plans")]])
    )
    await callback.answer()

# ========== АДМИНКА: БЭКАП ==========

@router.callback_query(F.data == "a_backup")
async def a_backup_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    await callback.message.edit_text("⏳ Бэкап...")
    result = GitHubBackup().backup_db()
    await callback.message.edit_text("✅ Бэкап создан!" if result else "❌ Ошибка", reply_markup=admin_kb())
    await callback.answer()

# ========== АДМИНКА: РАССЫЛКА ==========

@router.callback_query(F.data == "a_broadcast")
async def a_broadcast_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    user_pages[callback.from_user.id] = {"state": "waiting_broadcast"}
    await callback.message.edit_text("📢 **Рассылка**\n\nВведите текст.\n\n⏹ /cancel", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]]))
    await callback.answer()

# ========== ОБРАБОТКА АДМИН-ВВОДА ==========

async def handle_admin_input(message: types.Message):
    user_id = message.from_user.id
    state = user_pages.get(user_id, {})
    
    if state.get("state") == "waiting_plan_edit":
        if message.text == "/cancel":
            user_pages.pop(user_id, None)
            return await message.answer("✅ Отменено", reply_markup=admin_kb())
        try:
            parts = message.text.split()
            if len(parts) != 2:
                return await message.answer("❌ Формат: картинки символы", reply_markup=admin_kb())
            images, chars = int(parts[0]), int(parts[1])
            plan = state.get("plan")
            if plan == 'free':
                set_setting('image_limit_free', str(images))
                set_setting('free_input_chars', str(chars))
            elif plan == 'premium':
                set_setting('image_limit_premium', str(images))
                set_setting('premium_input_chars', str(chars))
            elif plan == 'deluxe':
                set_setting('image_limit_premium_deluxe', str(images))
                set_setting('premium_deluxe_input_chars', str(chars))
            await message.answer(f"✅ Обновлено: карт={images}, симв={chars}", reply_markup=admin_kb())
            do_backup()
            user_pages.pop(user_id, None)
        except:
            await message.answer("❌ Ошибка! Формат: картинки символы", reply_markup=admin_kb())
        return
    
    if state.get("state") == "waiting_broadcast":
        if message.text == "/cancel":
            user_pages.pop(user_id, None)
            return await message.answer("✅ Отменено", reply_markup=admin_kb())
        await message.answer("📢 Рассылка...")
        
        from database.db import get_db
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE is_blocked = 0")
            users = cursor.fetchall()
        
        sent = 0
        for u in users:
            try:
                await message.bot.send_message(u[0], f"📢 {message.text}")
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
        await message.answer("✅ Отправлено админу!", reply_markup=main_menu())
        user_pages.pop(user_id, None)
        return

@router.message(Command("cancel"))
async def cancel_cmd(message: types.Message):
    user_pages.pop(message.from_user.id, None)
    await message.answer("✅ Отменено", reply_markup=main_menu())
