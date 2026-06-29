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

def ensure_user(user_id, username=None):
    user = get_user(user_id)
    if not user:
        create_user(user_id, username or "")
        return get_user(user_id)
    return user

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
        [InlineKeyboardButton(text="⚙️ Управление тарифами", callback_data="a_plans")],
        [InlineKeyboardButton(text="💾 Бэкап", callback_data="a_backup"), InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

# === КОМАНДЫ ===
@router.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    ensure_user(user_id, username)
    
    args = message.text.split()
    if len(args) > 1 and args[1].isdigit() and int(args[1]) != user_id:
        add_referral(int(args[1]), user_id)
        await message.answer("👤 Вы приглашены! Реферер +5 запросов.")
    
    await message.answer(
        "🤖 **Vertex AI**\n\n🧠 ИИ в Telegram!\n✅ 10 запросов/день\n💎 Premium: безлимит\n👥 Приведи друга → +5 запросов\n\nПросто напиши вопрос!",
        reply_markup=main_menu()
    )

@router.message(Command("stats"))
async def stats_cmd(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    user = ensure_user(user_id, username)
    if not user:
        return await message.answer("❌ Ошибка! Нажми /start", reply_markup=main_menu())
    
    ok, rem = can_request(user_id)
    used, limit, prem, plan = get_image_stats(user_id)
    trial = get_trial_remaining(user_id)
    
    plan_names = {
        'basic': '🔴 Бесплатный',
        'premium': '💎 Premium',
        'premium_deluxe': '👑 Premium Deluxe'
    }
    
    text = f"📊 **Статистика**\n\n"
    text += f"📝 Запросов: {rem if not prem else '∞'}\n"
    text += f"🖼️ Картинок сегодня: {used}/{limit}\n"
    if trial > 0 and not prem:
        text += f"🎁 Пробный период: {trial} картинок\n"
    text += f"💎 План: {plan_names.get(plan, '🔴 Бесплатный')}"
    
    await message.answer(text, reply_markup=main_menu())

@router.message(Command("profile"))
async def profile_cmd(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    user = ensure_user(user_id, username)
    if not user:
        return await message.answer("❌ Ошибка! Нажми /start", reply_markup=main_menu())
    
    try:
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
        refs = cursor.fetchone()[0] or 0
    except:
        refs = 0
    
    used, limit, prem, plan = get_image_stats(user_id)
    plan_names = {
        'basic': '🔴 Бесплатный',
        'premium': '💎 Premium',
        'premium_deluxe': '👑 Premium Deluxe'
    }
    
    text = f"👤 **Профиль**\n\n"
    text += f"🆔 {user[0]}\n"
    text += f"📆 {user[2][:10] if user[2] else 'Нет'}\n"
    text += f"📊 Запросов: {user[5] or 0}\n"
    text += f"👥 Приглашено: {refs}\n"
    text += f"💎 План: {plan_names.get(plan, '🔴 Бесплатный')}\n"
    text += f"🖼️ Картинки сегодня: {used}/{limit}"
    
    await message.answer(text, reply_markup=main_menu())

@router.message(Command("subscribe"))
async def subscribe_cmd(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    ensure_user(user_id, username)
    
    await message.answer(
        "💎 **Выберите тариф Premium**\n\n"
        "📋 **Premium** — 49⭐/мес\n"
        "• Безлимит текстовых запросов\n"
        "• 50 картинок в день\n"
        "• Приоритетная обработка\n\n"
        "👑 **Premium Deluxe** — 99⭐/мес\n"
        "• Безлимит текстовых запросов\n"
        "• 200 картинок в день\n"
        "• Приоритетная обработка\n"
        "• Эксклюзивные промпты\n"
        "• VIP-поддержка",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="💎 Premium 49⭐", callback_data="pay_premium"),
                InlineKeyboardButton(text="👑 Deluxe 99⭐", callback_data="pay_deluxe")
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
    )

@router.message(Command("referral"))
async def referral_cmd(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    user = ensure_user(user_id, username)
    if not user:
        return await message.answer("❌ Ошибка! Нажми /start", reply_markup=main_menu())
    
    try:
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
        count = cursor.fetchone()[0] or 0
    except:
        count = 0
    
    link = f"https://t.me/Vertex1bot?start={user_id}"
    await message.answer(f"👥 **Рефералы**\n\nПриглашено: {count}\nБонус: +5 запросов\n\n🔗 {link}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться", url=f"https://t.me/share/url?url={link}&text=🤖 Присоединяйся к Vertex AI!")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ]))

@router.message(Command("help"))
async def help_cmd(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    ensure_user(user_id, username)
    text = "❓ **Помощь**\n\n/start — меню\n/profile — профиль\n/stats — статистика\n/subscribe — Premium\n/referral — рефералы\n\n💎 Premium: безлимит + 50 картинок/день\n👑 Premium Deluxe: безлимит + 200 картинок/день"
    await message.answer(text, reply_markup=main_menu())

# === ОБРАБОТКА ТЕКСТА ===
@router.message(F.text)
async def handle_message(message: types.Message):
    if message.text.startswith("/"):
        return
    
    user_id = message.from_user.id
    
    # === ПРОВЕРЯЕМ СОСТОЯНИЯ АДМИНА (ЭТО ВАЖНО!) ===
    state = user_pages.get(user_id, {})
    if state.get("state") == "waiting_plan_edit":
        await handle_admin_input(message)
        return
    
    if state.get("state") == "waiting_premium_user":
        await handle_admin_input(message)
        return
    
    if state.get("state") == "waiting_broadcast":
        await handle_admin_input(message)
        return
    
    if state.get("state") == "waiting_contact":
        await handle_admin_input(message)
        return
    
    # === ОБЫЧНЫЙ ПОЛЬЗОВАТЕЛЬ ===
    username = message.from_user.username or ""
    user = ensure_user(user_id, username)
    if not user:
        await message.answer("👋 Нажми /start", reply_markup=main_menu())
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
        await message.answer("🔒 Лимит исчерпан! /subscribe")
        return
    
    prem = is_premium(user_id)
    status_msg = await message.answer("🤔 Думаю...")
    try:
        answer = solve_problem(message.text, "chat", prem)
        add_request(user_id)
        await status_msg.edit_text(f"🧠 {answer}\n\n{'∞' if prem else rem-1} запросов осталось")
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def generate_image(message: types.Message):
    user_id = message.from_user.id
    
    if not API_KEY:
        await message.answer("❌ API ключ не настроен")
        return
    
    trial_rem = get_trial_remaining(user_id)
    used, limit, prem, plan = get_image_stats(user_id)
    
    if prem:
        can_gen = used < limit
    elif trial_rem > 0:
        can_gen = True
        limit = 5
    else:
        can_gen, _ = can_generate_image(user_id)
    
    if not can_gen:
        await message.answer(f"❌ Лимит картинок исчерпан! {used}/{limit}\n💎 /subscribe")
        return
    
    status_msg = await message.answer("🎨 Генерирую картинку...")
    
    try:
        user_prompt = message.text
        
        prompt_resp = requests.post(
            "https://openai.bothub.chat/v1/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "model": PROMPT_MODEL,
                "messages": [
                    {"role": "system", "content": "Create detailed English prompt for Flux/Stable Diffusion. Only the prompt, no explanations!"},
                    {"role": "user", "content": f"Prompt for: {user_prompt}"}
                ],
                "max_tokens": 200,
                "temperature": 0.7
            },
            timeout=30
        )
        
        enhanced = user_prompt
        if prompt_resp.status_code == 200:
            enhanced = prompt_resp.json().get('choices', [{}])[0].get('message', {}).get('content', user_prompt).strip('"')
        
        for p in [10, 25, 45, 60, 75, 90]:
            await asyncio.sleep(0.2)
            try:
                await status_msg.edit_text(f"🎨 Генерирую картинку... {p}%")
            except:
                pass
        
        img_resp = requests.post(
            "https://bothub.chat/api/v2/replicate/v1/images/generations",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "model": IMAGE_MODEL,
                "input": {
                    "prompt": enhanced,
                    "aspect_ratio": "1:1",
                    "output_format": "webp"
                },
                "bothub": {
                    "include_usage": True,
                    "return_base64": False
                }
            },
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
                    await status_msg.edit_text("🎨 Генерирую картинку... 100% ✅")
                    await asyncio.sleep(0.2)
                    
                    if trial_rem > 0:
                        use_trial_image(user_id)
                    else:
                        add_image_request(user_id)
                    
                    new_used, new_limit, new_prem, new_plan = get_image_stats(user_id)
                    remaining = new_limit - new_used
                    
                    plan_emoji = "💎 Premium" if new_plan == 'premium' else "👑 Premium Deluxe" if new_plan == 'premium_deluxe' else "🔴 Бесплатный"
                    
                    await message.answer_photo(
                        BufferedInputFile(file=img_data.content, filename="image.webp"),
                        caption=f"🖼️ **Твоя картинка**\n📝 {user_prompt[:50]}...\n\n📊 Осталось картинок: {remaining}\n💎 План: {plan_emoji}"
                    )
                    
                    await status_msg.delete()
                    return
        
        await status_msg.edit_text("❌ Не удалось получить картинку. Попробуй другой запрос.")
        
    except Exception as e:
        logger.error(f"❌ Ошибка генерации: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

# === CALLBACK'и ===
@router.callback_query(F.data.in_(["mode_text", "mode_image"]))
async def set_mode(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or ""
    ensure_user(user_id, username)
    mode = callback.data.replace("mode_", "")
    user_modes[user_id] = mode
    await callback.answer(f"✅ Режим: {'🧠 Текст' if mode == 'text' else '🖼️ Картинка'}", show_alert=True)
    await callback.message.edit_text(
        f"{'🧠 **Режим Текст**' if mode == 'text' else '🖼️ **Режим Картинка**'}\n\nГотов к работе!",
        reply_markup=main_menu()
    )

@router.callback_query(F.data == "stats")
async def stats_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or ""
    user = ensure_user(user_id, username)
    if not user:
        await callback.message.edit_text("❌ Ошибка! Нажми /start", reply_markup=main_menu())
        await callback.answer()
        return
    
    class FakeMessage:
        def __init__(self, uid, uname):
            self.from_user = type('obj', (object,), {'id': uid, 'username': uname})()
            self.answer = callback.message.answer
    await stats_cmd(FakeMessage(user_id, username))
    await callback.answer()

@router.callback_query(F.data == "profile")
async def profile_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or ""
    user = ensure_user(user_id, username)
    if not user:
        await callback.message.edit_text("❌ Ошибка! Нажми /start", reply_markup=main_menu())
        await callback.answer()
        return
    
    class FakeMessage:
        def __init__(self, uid, uname):
            self.from_user = type('obj', (object,), {'id': uid, 'username': uname})()
            self.answer = callback.message.answer
    await profile_cmd(FakeMessage(user_id, username))
    await callback.answer()

@router.callback_query(F.data == "referral")
async def referral_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or ""
    user = ensure_user(user_id, username)
    if not user:
        await callback.message.edit_text("❌ Ошибка! Нажми /start", reply_markup=main_menu())
        await callback.answer()
        return
    
    class FakeMessage:
        def __init__(self, uid, uname):
            self.from_user = type('obj', (object,), {'id': uid, 'username': uname})()
            self.answer = callback.message.answer
    await referral_cmd(FakeMessage(user_id, username))
    await callback.answer()

@router.callback_query(F.data == "premium")
async def premium_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or ""
    ensure_user(user_id, username)
    await subscribe_cmd(callback.message)
    await callback.answer()

@router.callback_query(F.data == "help")
async def help_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or ""
    ensure_user(user_id, username)
    await help_cmd(callback.message)
    await callback.answer()

@router.callback_query(F.data == "leaderboard")
async def leaderboard_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or ""
    ensure_user(user_id, username)
    cursor.execute("SELECT user_id, username, total_requests FROM users ORDER BY total_requests DESC LIMIT 10")
    users = cursor.fetchall()
    if not users:
        return await callback.answer("Нет данных")
    text = "🏆 **Рейтинг**\n\n" + "\n".join([f"{'🥇🥈🥉'[i] if i<3 else f'{i+1}.'} `{u[0]}` — {u[1] or 'без имени'} — {u[2]} задач" for i, u in enumerate(users)])
    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()

@router.callback_query(F.data == "contact_admin")
async def contact_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or ""
    ensure_user(user_id, username)
    user_pages[user_id] = {"state": "waiting_contact"}
    await callback.message.edit_text("📩 Напишите сообщение админу.\n⏹ /cancel", reply_markup=main_menu())
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def back_main_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or ""
    ensure_user(user_id, username)
    await callback.message.edit_text("🤖 **Vertex AI**\n\nПросто напиши вопрос!", reply_markup=main_menu())
    await callback.answer()

# === ПЛАТЕЖИ ===
@router.callback_query(F.data.startswith("pay_"))
async def pay_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or ""
    ensure_user(user_id, username)
    try:
        plan_type = callback.data.replace("pay_", "")
        
        if plan_type == "premium":
            stars = 49
            days = 30
            plan = "premium"
            title = "Premium 1 мес"
            desc = "Безлимит + 50 картинок/день"
        elif plan_type == "deluxe":
            stars = 99
            days = 30
            plan = "premium_deluxe"
            title = "Premium Deluxe 1 мес"
            desc = "Безлимит + 200 картинок/день"
        else:
            await callback.answer("❌ Неверный тариф", show_alert=True)
            return
        
        payload = secrets.token_hex(16)
        
        cursor.execute("INSERT INTO payments (user_id, stars_amount, telegram_payload, status, timestamp, plan) VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, stars, payload, "pending", datetime.now().isoformat(), plan))
        conn.commit()
        
        await callback.bot.send_invoice(
            chat_id=user_id,
            title=title,
            description=desc,
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=title, amount=stars)],
            start_parameter="premium_sub"
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"❌ Ошибка платежа: {e}")
        await callback.answer("❌ Ошибка создания платежа", show_alert=True)

@router.pre_checkout_query()
async def pre_checkout(query: types.PreCheckoutQuery):
    await query.answer(ok=True)

@router.message(F.successful_payment)
async def payment_success(message: types.Message):
    payload = message.successful_payment.invoice_payload
    cursor.execute("SELECT stars_amount, plan FROM payments WHERE telegram_payload = ?", (payload,))
    row = cursor.fetchone()
    
    if row:
        stars, plan = row
        days = 30
        add_premium(message.from_user.id, days, plan)
        cursor.execute("UPDATE payments SET status = 'completed' WHERE telegram_payload = ?", (payload,))
        conn.commit()
        GitHubBackup().backup_db()
        
        plan_names = {
            'premium': '💎 Premium',
            'premium_deluxe': '👑 Premium Deluxe'
        }
        
        await message.answer(f"✅ {plan_names.get(plan, 'Premium')} на 30 дней активирован!")
    else:
        await message.answer("❌ Ошибка активации. Обратитесь к админу.")

# === АДМИНКА ===
@router.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if is_admin(message.from_user.id):
        await message.answer("🛡️ **АДМИН-ПАНЕЛЬ**", reply_markup=admin_kb())
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
        await callback.message.edit_text("🛡️ **АДМИН-ПАНЕЛЬ**", reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_stats")
async def a_stats_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    total, prem, req = get_stats()
    cursor.execute("SELECT COUNT(*) FROM users WHERE plan = 'premium_deluxe' AND premium_until > datetime('now')")
    deluxe = cursor.fetchone()[0] or 0
    
    await callback.message.edit_text(
        f"📊 **Статистика**\n\n"
        f"👥 Всего: {total}\n"
        f"💎 Premium: {prem - deluxe}\n"
        f"👑 Premium Deluxe: {deluxe}\n"
        f"📝 Запросов: {req}",
        reply_markup=admin_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "a_users")
async def a_users_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    cursor.execute("SELECT user_id, username, total_requests, plan, is_blocked FROM users ORDER BY user_id LIMIT 20")
    users = cursor.fetchall()
    
    plan_emoji = {
        'basic': '🔴',
        'premium': '💎',
        'premium_deluxe': '👑'
    }
    
    if not users:
        text = "👥 Пользователей не найдено"
    else:
        text = "👥 **Пользователи**\n\n"
        for u in users:
            emoji = plan_emoji.get(u[3], '🔴')
            blocked = "🚫" if u[4] == 1 else "✅"
            text += f"{blocked} {emoji} `{u[0]}` — {u[1] or 'без имени'} — {u[2]} запросов\n"
    
    await callback.message.edit_text(text, reply_markup=admin_kb())
    await callback.answer()

# === УПРАВЛЕНИЕ ТАРИФАМИ ===
@router.callback_query(F.data == "a_plans")
async def a_plans_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    text = (
        "⚙️ **Управление тарифами**\n\n"
        "Текущие лимиты:\n\n"
        f"🔹 **Бесплатный**\n"
        f"  Картинок: {get_setting('image_limit_free')}\n"
        f"  Символов: {get_setting('free_input_chars')}\n\n"
        f"💎 **Premium**\n"
        f"  Картинок: {get_setting('image_limit_premium')}\n"
        f"  Символов: {get_setting('premium_input_chars')}\n\n"
        f"👑 **Premium Deluxe**\n"
        f"  Картинок: {get_setting('image_limit_premium_deluxe')}\n"
        f"  Символов: {get_setting('premium_deluxe_input_chars')}\n\n"
        "Используйте команды:\n"
        "/set_plan ID basic|premium|premium_deluxe - сменить план\n"
        "/remove_premium ID - отключить Premium\n"
        "/block ID - заблокировать\n"
        "/unblock ID - разблокировать"
    )
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔹 Изменить бесплатный", callback_data="edit_free")],
        [InlineKeyboardButton(text="💎 Изменить Premium", callback_data="edit_premium")],
        [InlineKeyboardButton(text="👑 Изменить Premium Deluxe", callback_data="edit_deluxe")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ]))
    await callback.answer()

# === ИЗМЕНЕНИЕ ЛИМИТОВ ДЛЯ ТАРИФОВ ===
@router.callback_query(F.data.startswith("edit_"))
async def edit_plan_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    plan = callback.data.replace("edit_", "")
    
    plan_names = {
        'free': '🔹 Бесплатный',
        'premium': '💎 Premium',
        'deluxe': '👑 Premium Deluxe'
    }
    
    # Сохраняем состояние
    user_pages[callback.from_user.id] = {"state": "waiting_plan_edit", "plan": plan}
    
    await callback.message.edit_text(
        f"⚙️ **Изменение {plan_names.get(plan, 'тарифа')}**\n\n"
        f"Введите через пробел:\n"
        f"`<кол-во_картинок> <кол-во_символов>`\n\n"
        f"Пример: `10 1000`\n"
        f"(10 картинок в день, 1000 символов за запрос)\n\n"
        f"⏹ Отмена: /cancel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="a_plans")]
        ])
    )
    await callback.answer()

# === ОБРАБОТЧИК АДМИН-ВВОДА ===
async def handle_admin_input(message: types.Message):
    user_id = message.from_user.id
    state = user_pages.get(user_id, {})
    
    # === РЕДАКТИРОВАНИЕ ТАРИФОВ ===
    if state.get("state") == "waiting_plan_edit":
        if message.text == "/cancel":
            user_pages.pop(user_id, None)
            await message.answer("✅ Отменено", reply_markup=admin_kb())
            return
        
        try:
            parts = message.text.split()
            if len(parts) != 2:
                await message.answer("❌ Формат: кол-во_картинок кол-во_символов\nПример: `10 1000`", reply_markup=admin_kb())
                return
            
            images, chars = int(parts[0]), int(parts[1])
            plan = state.get("plan")
            
            if plan == 'free':
                set_setting('image_limit_free', str(images))
                set_setting('free_input_chars', str(chars))
                await message.answer(f"✅ Бесплатный тариф обновлён:\nКартинок: {images}\nСимволов: {chars}", reply_markup=admin_kb())
            elif plan == 'premium':
                set_setting('image_limit_premium', str(images))
                set_setting('premium_input_chars', str(chars))
                await message.answer(f"✅ Premium обновлён:\nКартинок: {images}\nСимволов: {chars}", reply_markup=admin_kb())
            elif plan == 'deluxe':
                set_setting('image_limit_premium_deluxe', str(images))
                set_setting('premium_deluxe_input_chars', str(chars))
                await message.answer(f"✅ Premium Deluxe обновлён:\nКартинок: {images}\nСимволов: {chars}", reply_markup=admin_kb())
            else:
                await message.answer("❌ Неизвестный тариф", reply_markup=admin_kb())
            
            user_pages.pop(user_id, None)
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}\nФормат: кол-во_картинок кол-во_символов", reply_markup=admin_kb())
        return
    
    # === ВЫДАЧА PREMIUM ПОЛЬЗОВАТЕЛЮ ===
    if state.get("state") == "waiting_premium_user":
        if message.text == "/cancel":
            user_pages.pop(user_id, None)
            await message.answer("✅ Отменено", reply_markup=admin_kb())
            return
        
        try:
            parts = message.text.split()
            if len(parts) == 2:
                user_id, plan = int(parts[0]), parts[1]
                if plan not in ['premium', 'premium_deluxe']:
                    await message.answer("❌ План должен быть: premium или premium_deluxe", reply_markup=admin_kb())
                    return
                add_premium(user_id, 30, plan)
                await message.answer(f"✅ {plan} на 30 дней выдан пользователю {user_id}", reply_markup=admin_kb())
            elif len(parts) == 3:
                user_id, plan, days = int(parts[0]), parts[1], int(parts[2])
                if plan not in ['premium', 'premium_deluxe']:
                    await message.answer("❌ План должен быть: premium или premium_deluxe", reply_markup=admin_kb())
                    return
                add_premium(user_id, days, plan)
                await message.answer(f"✅ {plan} на {days} дней выдан пользователю {user_id}", reply_markup=admin_kb())
            else:
                await message.answer("❌ Формат: ID план [дни]\nПример: `123456 premium 30`", reply_markup=admin_kb())
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}", reply_markup=admin_kb())
        user_pages.pop(user_id, None)
        return
    
    # === РАССЫЛКА ===
    if state.get("state") == "waiting_broadcast":
        if message.text == "/cancel":
            user_pages.pop(user_id, None)
            await message.answer("✅ Отменено", reply_markup=admin_kb())
            return
        
        await message.answer("📢 Рассылка...")
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
        user_pages.pop(user_id, None)
        return
    
    # === ОБРАЩЕНИЕ В АДМИНКУ ===
    if state.get("state") == "waiting_contact":
        cursor.execute("INSERT INTO messages_to_admin (user_id, username, text, date) VALUES (?, ?, ?, ?)",
                    (user_id, message.from_user.username or "", message.text, datetime.now().isoformat()))
        conn.commit()
        await message.bot.send_message(int(os.getenv('ADMIN_ID', 6957852385)), f"📩 От {user_id}:\n{message.text}")
        await message.answer("✅ Отправлено админу!", reply_markup=main_menu())
        user_pages.pop(user_id, None)
        return

# === ДОПОЛНИТЕЛЬНЫЕ АДМИН-КОМАНДЫ ===
@router.message(Command("block"))
async def block_user(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        return
    
    try:
        parts = message.text.split()
        user_id = int(parts[1])
        cursor.execute("UPDATE users SET is_blocked = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        await message.answer(f"🚫 Пользователь {user_id} заблокирован", reply_markup=admin_kb())
    except:
        await message.answer("❌ Использование: /block ID", reply_markup=admin_kb())

@router.message(Command("unblock"))
async def unblock_user(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        return
    
    try:
        parts = message.text.split()
        user_id = int(parts[1])
        cursor.execute("UPDATE users SET is_blocked = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
        await message.answer(f"✅ Пользователь {user_id} разблокирован", reply_markup=admin_kb())
    except:
        await message.answer("❌ Использование: /unblock ID", reply_markup=admin_kb())

@router.message(Command("set_plan"))
async def set_plan_user(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        return
    
    try:
        parts = message.text.split()
        user_id, plan = int(parts[1]), parts[2]
        if plan not in ['basic', 'premium', 'premium_deluxe']:
            await message.answer("❌ План должен быть: basic, premium или premium_deluxe", reply_markup=admin_kb())
            return
        
        cursor.execute("UPDATE users SET plan = ? WHERE user_id = ?", (plan, user_id))
        conn.commit()
        await message.answer(f"✅ План {plan} установлен для {user_id}", reply_markup=admin_kb())
    except:
        await message.answer("❌ Использование: /set_plan ID basic|premium|premium_deluxe", reply_markup=admin_kb())

@router.message(Command("remove_premium"))
async def remove_premium(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        return
    
    try:
        parts = message.text.split()
        user_id = int(parts[1])
        cursor.execute("UPDATE users SET premium_until = NULL, plan = 'basic' WHERE user_id = ?", (user_id,))
        conn.commit()
        await message.answer(f"✅ Premium отключён для {user_id}", reply_markup=admin_kb())
    except:
        await message.answer("❌ Использование: /remove_premium ID", reply_markup=admin_kb())

@router.callback_query(F.data == "a_give_premium")
async def a_give_premium_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    user_pages[callback.from_user.id] = {"state": "waiting_premium_user"}
    await callback.message.edit_text(
        "💎 **Выдать Premium**\n\n"
        "Формат: `ID план [дни]`\n\n"
        "Примеры:\n"
        "`123456 premium 30` — Premium на 30 дней\n"
        "`123456 premium_deluxe` — Premium Deluxe на 30 дней\n\n"
        "Доступные планы: premium, premium_deluxe",
        reply_markup=admin_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "a_broadcast")
async def a_broadcast_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    user_pages[callback.from_user.id] = {"state": "waiting_broadcast"}
    await callback.message.edit_text("📢 Введи текст рассылки", reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_backup")
async def a_backup_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    await callback.message.edit_text("⏳ Создаю бэкап...")
    result = GitHubBackup().backup_db()
    await callback.message.edit_text("✅ Бэкап создан!" if result else "❌ Ошибка", reply_markup=admin_kb())
    await callback.answer()

@router.message(Command("cancel"))
async def cancel_cmd(message: types.Message):
    user_pages.pop(message.from_user.id, None)
    await message.answer("✅ Отменено", reply_markup=main_menu())
