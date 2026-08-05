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
from PIL import Image, ImageDraw, ImageFont

router = Router()
logger = logging.getLogger(__name__)
user_modes = {}
user_pages = {}
ADMIN_CODE = "30121979"
API_KEY = os.getenv('OPENAI_API_KEY')
PROVIDER_TOKEN = os.getenv('PROVIDER_TOKEN', '')
IMAGE_MODEL = "flux-schnell"
PROMPT_MODEL = "gpt-4.1-nano"

plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['font.size'] = 10

# ===== ФУНКЦИИ РАБОТЫ С ТОКЕНАМИ =====
def get_tokens(user_id):
    """Получить баланс токенов пользователя"""
    user = get_user(user_id)
    if not user:
        return 0
    return user.get('tokens', 0)

def add_tokens(user_id, amount):
    """Добавить токены пользователю"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET tokens = tokens + ? WHERE user_id = ?", (amount, user_id))
        return True

def spend_tokens(user_id, amount):
    """Списать токены (возвращает True если достаточно)"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT tokens FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row and row[0] >= amount:
            cursor.execute("UPDATE users SET tokens = tokens - ? WHERE user_id = ?", (amount, user_id))
            return True
        return False

def has_trial(user_id):
    """Проверить, активен ли пробный период"""
    user = get_user(user_id)
    if not user:
        return False
    trial_start = user.get('trial_start')
    if not trial_start:
        return False
    try:
        start_date = datetime.fromisoformat(trial_start)
        return (datetime.now() - start_date).days < 3
    except:
        return False

def activate_trial(user_id):
    """Активировать пробный период (20 токенов)"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET trial_start = ?, tokens = tokens + 20 WHERE user_id = ?", 
                      (datetime.now().isoformat(), user_id))
        return True

def get_trial_remaining(user_id):
    """Сколько осталось дней пробного периода"""
    user = get_user(user_id)
    if not user:
        return 0
    trial_start = user.get('trial_start')
    if not trial_start:
        return 0
    try:
        start_date = datetime.fromisoformat(trial_start)
        days_passed = (datetime.now() - start_date).days
        return max(0, 3 - days_passed)
    except:
        return 0

def add_watermark(image_data):
    try:
        img = Image.open(BytesIO(image_data))
        draw = ImageDraw.Draw(img)
        font_size = 30
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except:
            font = ImageFont.load_default()
        text = "Vertex AI"
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        except:
            text_width = 100
            text_height = 30
        position = (img.width - text_width - 20, img.height - text_height - 20)
        shadow = Image.new('RGBA', (text_width + 40, text_height + 20), (0, 0, 0, 100))
        img.paste(shadow, (position[0] - 20, position[1] - 10), shadow)
        draw.text(position, text, font=font, fill=(255, 255, 255, 255))
        output = BytesIO()
        img.save(output, format='PNG')
        output.seek(0)
        return output
    except Exception as e:
        print(f"⚠️ Ошибка водяного знака: {e}")
        return None

def force_create_user(user_id, username=None):
    try:
        user = get_user(user_id)
        if user:
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

def log_admin_action(admin_id, action, target_id, details):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO admin_log (admin_id, action, target_id, details, timestamp) VALUES (?, ?, ?, ?, ?)",
                      (admin_id, action, target_id, details, datetime.now().isoformat()))

def use_promocode(code, user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, bonus_tokens, max_uses, used FROM promocodes WHERE code = ? AND expires_at > datetime('now')", (code,))
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
        if promo['bonus_tokens'] > 0:
            cursor.execute("UPDATE users SET tokens = tokens + ? WHERE user_id = ?", (promo['bonus_tokens'], user_id))
        return True, f"✅ Промокод активирован! +{promo['bonus_tokens']} токенов!"

# ===== МЕНЮ =====
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼️ Сгенерировать", callback_data="generate_image")],
        [InlineKeyboardButton(text="✨ Купить токены", callback_data="buy_tokens"), InlineKeyboardButton(text="📊 Баланс", callback_data="balance")],
        [InlineKeyboardButton(text="🎁 Промокод", callback_data="promo_use"), InlineKeyboardButton(text="👥 Рефералы", callback_data="referral")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"), InlineKeyboardButton(text="📩 Поддержка", callback_data="contact_admin")],
        [InlineKeyboardButton(text="🛡️ Админ", callback_data="admin_panel"), InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ])

def admin_kb():
    new_messages = get_messages_count()
    badge = f" ({new_messages})" if new_messages > 0 else ""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="a_stats"), InlineKeyboardButton(text="👥 Пользователи", callback_data="a_users")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="a_broadcast"), InlineKeyboardButton(text="🚫 Блокировка", callback_data="a_block")],
        [InlineKeyboardButton(text="💾 Бэкап", callback_data="a_backup"), InlineKeyboardButton(text="📩 Обращения", callback_data="a_messages")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

# ===== КОМАНДЫ =====
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
    
    # Активируем пробный период, если ещё не активирован
    if not has_trial(user_id) and not get_tokens(user_id):
        activate_trial(user_id)
        trial_text = "🎁 Тебе подарок! 20 токенов (2 картинки) бесплатно на 3 дня!"
    else:
        trial_text = ""
    
    tokens = get_tokens(user_id)
    text = (
        f"🤖 **Vertex AI**\n\n"
        f"💰 Токенов: {tokens}\n"
        f"🖼️ 10 токенов = 1 картинка\n\n"
        f"✨ Покупай токены и генерируй картинки!\n"
        f"{trial_text}\n\n"
        f"Просто нажми «Сгенерировать»!"
    )
    await message.answer(text, reply_markup=main_menu())

@router.message(Command("balance"))
async def balance_cmd(message: types.Message):
    user_id = message.from_user.id
    user = force_create_user(user_id, message.from_user.username or "")
    if not user:
        await message.answer("❌ Ошибка!", reply_markup=main_menu())
        return
    tokens = get_tokens(user_id)
    trial = get_trial_remaining(user_id)
    text = f"💰 **Баланс токенов**\n\n"
    text += f"🪙 Токенов: {tokens}\n"
    text += f"🖼️ Хватит на: {tokens // 10} картинок\n"
    if trial > 0:
        text += f"🎁 Пробный период: {trial} дней\n"
    await message.answer(text, reply_markup=main_menu())

@router.message(Command("profile"))
async def profile_cmd(message: types.Message):
    user_id = message.from_user.id
    user = force_create_user(user_id, message.from_user.username or "")
    if not user:
        await message.answer("❌ Ошибка!", reply_markup=main_menu())
        return
    tokens = get_tokens(user_id)
    text = (
        f"👤 **Мой профиль**\n\n"
        f"🆔 ID: {user['user_id']}\n"
        f"👤 Имя: {user['username'] or 'без имени'}\n"
        f"💰 Токенов: {tokens}\n"
        f"🖼️ Картинок: {tokens // 10}\n"
    )
    await message.answer(text, reply_markup=main_menu())

@router.message(Command("help"))
async def help_cmd(message: types.Message):
    text = (
        "❓ **Помощь**\n\n"
        "🖼️ Сгенерировать — создать картинку (10 токенов)\n"
        "✨ Купить токены — пополнить баланс\n"
        "📊 Баланс — проверить токены\n"
        "🎁 Промокод — активировать бонус\n"
        "👥 Рефералы — приглашай друзей\n\n"
        "📌 Команды:\n"
        "/start — меню\n"
        "/balance — баланс\n"
        "/profile — профиль\n"
        "/help — помощь"
    )
    await message.answer(text, reply_markup=main_menu())

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
    
    if state.get("state") in ["waiting_broadcast", "waiting_block_user", "waiting_contact"]:
        await handle_admin_input(message)
        return
    
    # Любой текст = генерация картинки
    await generate_image(message)

async def generate_image(message: types.Message):
    user_id = message.from_user.id
    user = force_create_user(user_id, message.from_user.username or "")
    if not user:
        await message.answer("❌ Ошибка! Попробуйте позже.", reply_markup=main_menu())
        return
    
    # Проверяем токены
    tokens = get_tokens(user_id)
    if tokens < 10:
        trial = get_trial_remaining(user_id)
        if trial > 0:
            await message.answer(
                f"⚠️ У тебя осталось {tokens} токенов.\n"
                f"🎁 Пробный период: {trial} дней\n"
                f"Пополни баланс или используй пробные токены.",
                reply_markup=main_menu()
            )
            return
        await message.answer(
            "❌ Недостаточно токенов!\n"
            f"Нужно: 10 токенов\n"
            f"У тебя: {tokens}\n\n"
            "✨ Купи токены или активируй промокод.",
            reply_markup=main_menu()
        )
        return
    
    if not API_KEY:
        return await message.answer("❌ API ключ не настроен")
    
    status_msg = await message.answer("🎨 Генерирую картинку...")
    try:
        user_prompt = message.text
        
        # Генерация промпта
        prompt_resp = requests.post(
            "https://openai.bothub.chat/v1/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={"model": PROMPT_MODEL, "messages": [{"role": "system", "content": "Create detailed English prompt for Flux. Only the prompt!"}, {"role": "user", "content": f"Prompt for: {user_prompt}"}], "max_tokens": 200},
            timeout=30
        )
        enhanced = user_prompt
        if prompt_resp.status_code == 200:
            enhanced = prompt_resp.json().get('choices', [{}])[0].get('message', {}).get('content', user_prompt).strip('"')
        
        # Прогресс
        for p in range(5, 101, 5):
            await asyncio.sleep(0.3)
            try:
                await status_msg.edit_text(f"🎨 {p}%")
            except:
                pass
        
        # Генерация картинки
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
                    
                    # Добавляем водяной знак
                    watermarked = add_watermark(img_data.content)
                    if watermarked:
                        img_data = watermarked
                    
                    # Списываем токены
                    spend_tokens(user_id, 10)
                    
                    # Сохраняем статистику
                    do_backup()
                    
                    new_tokens = get_tokens(user_id)
                    await message.answer_photo(
                        BufferedInputFile(file=img_data.getvalue() if hasattr(img_data, 'getvalue') else img_data.content, filename="image.png"),
                        caption=f"🖼️ **Твоя картинка**\n📝 {user_prompt[:50]}...\n\n💰 Осталось токенов: {new_tokens}\n🖼️ Ещё картинок: {new_tokens // 10}"
                    )
                    await status_msg.delete()
                    return
        
        await status_msg.edit_text("❌ Не удалось получить картинку")
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

# ===== CALLBACK'И =====
@router.callback_query(F.data == "generate_image")
async def generate_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = force_create_user(user_id, callback.from_user.username or "")
    if not user:
        await callback.answer("❌ Ошибка!", show_alert=True)
        return
    tokens = get_tokens(user_id)
    if tokens < 10:
        trial = get_trial_remaining(user_id)
        await callback.answer(f"❌ Нужно 10 токенов. У тебя: {tokens}" + (f"\n🎁 Пробный период: {trial} дней" if trial > 0 else ""), show_alert=True)
        return
    await callback.message.edit_text(
        "✏️ **Напиши описание картинки**\n\n"
        "Просто напиши что хочешь увидеть.\n"
        "Например: «кот в космосе»\n\n"
        f"💰 У тебя: {tokens} токенов\n"
        f"🖼️ 1 картинка = 10 токенов",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
    )
    await callback.answer()

@router.callback_query(F.data == "balance")
async def balance_cb(callback: types.CallbackQuery):
    await balance_cmd(callback.message)
    await callback.answer()

@router.callback_query(F.data == "profile")
async def profile_cb(callback: types.CallbackQuery):
    await profile_cmd(callback.message)
    await callback.answer()

@router.callback_query(F.data == "referral")
async def referral_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = force_create_user(user_id, callback.from_user.username or "")
    if not user:
        await callback.answer("❌ Ошибка!", show_alert=True)
        return
    count = get_referral_count(user_id)
    bonus_images, bonus_requests = get_referral_bonuses(user_id)
    link = f"https://t.me/Vertex1bot?start={user_id}"
    text = (
        "👥 **Рефералы**\n\n"
        f"👤 Приглашено: {count}\n"
        f"🎁 Бонус: +10 токенов за друга\n\n"
        f"🔗 Твоя ссылка:\n{link}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться", url=f"https://t.me/share/url?url={link}&text=🤖 Присоединяйся к Vertex AI!")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
    )
    await callback.answer()

@router.callback_query(F.data == "promo_use")
async def promo_use_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    user_pages[user_id] = {"state": "waiting_promo_use"}
    await callback.message.edit_text(
        "🎁 **Введите промокод**\n\n"
        "Напиши код, чтобы получить бонусные токены:\n\n"
        "⏹ /cancel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
    )
    await callback.answer()

@router.callback_query(F.data == "buy_tokens")
async def buy_tokens_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 100 токенов (10 карт) — 10⭐", callback_data="token_100")],
        [InlineKeyboardButton(text="📦 500 токенов (50 карт) — 40⭐", callback_data="token_500")],
        [InlineKeyboardButton(text="📦 1000 токенов (100 карт) — 70⭐", callback_data="token_1000")],
        [InlineKeyboardButton(text="📦 5000 токенов (500 карт) — 300⭐", callback_data="token_5000")],
        [InlineKeyboardButton(text="📦 10000 токенов (1000 карт) — 500⭐", callback_data="token_10000")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(
        "✨ **Купить токены**\n\n"
        "💰 100 токенов (10 карт) — 10⭐\n"
        "💰 500 токенов (50 карт) — 40⭐\n"
        "💰 1000 токенов (100 карт) — 70⭐\n"
        "💰 5000 токенов (500 карт) — 300⭐\n"
        "💰 10000 токенов (1000 карт) — 500⭐\n\n"
        "Выберите пакет:",
        reply_markup=kb
    )
    await callback.answer()

@router.callback_query(F.data.startswith("token_"))
async def token_pay_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    
    packs = {
        '100': (10, 100),
        '500': (40, 500),
        '1000': (70, 1000),
        '5000': (300, 5000),
        '10000': (500, 10000)
    }
    pack_type = callback.data.replace("token_", "")
    if pack_type not in packs:
        return await callback.answer("❌ Неверный пакет", show_alert=True)
    stars, tokens = packs[pack_type]
    payload = secrets.token_hex(16)
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO payments (user_id, stars_amount, telegram_payload, status, timestamp, plan) VALUES (?, ?, ?, ?, ?, ?)",
                      (user_id, stars, payload, "pending", datetime.now().isoformat(), "tokens"))
    await callback.bot.send_invoice(
        chat_id=user_id,
        title=f"📦 {tokens} токенов",
        description=f"{tokens} токенов = {tokens//10} картинок",
        payload=payload,
        provider_token=PROVIDER_TOKEN,
        currency="XTR",
        prices=[LabeledPrice(label=f"{tokens} токенов", amount=stars)],
        start_parameter="buy_tokens"
    )
    await callback.answer()

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
        if plan == "tokens":
            if stars == 10:
                tokens = 100
            elif stars == 40:
                tokens = 500
            elif stars == 70:
                tokens = 1000
            elif stars == 300:
                tokens = 5000
            elif stars == 500:
                tokens = 10000
            else:
                tokens = 0
            if tokens > 0:
                add_tokens(message.from_user.id, tokens)
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE payments SET status = 'completed' WHERE telegram_payload = ?", (payload,))
                await message.answer(f"✅ Оплачено! Ты получил +{tokens} токенов!", reply_markup=main_menu())
            else:
                await message.answer("❌ Ошибка активации")
        elif plan in ['premium', 'premium_deluxe']:
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
    else:
        await message.answer("❌ Ошибка активации")

@router.callback_query(F.data == "contact_admin")
async def contact_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    user_pages[user_id] = {"state": "waiting_contact"}
    await callback.message.edit_text("📩 Напишите сообщение админу.\n\n⏹ /cancel", reply_markup=main_menu())
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def back_main_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    tokens = get_tokens(user_id)
    text = (
        f"🤖 **Vertex AI**\n\n"
        f"💰 Токенов: {tokens}\n"
        f"🖼️ 10 токенов = 1 картинка\n\n"
        f"Напиши описание или нажми «Сгенерировать»!"
    )
    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()

@router.callback_query(F.data == "help")
async def help_cb(callback: types.CallbackQuery):
    await help_cmd(callback.message)
    await callback.answer()

@router.callback_query(F.data == "admin_panel")
async def admin_panel_cb(callback: types.CallbackQuery):
    if is_admin(callback.from_user.id):
        await callback.message.edit_text("🛡️ **АДМИН-ПАНЕЛЬ**", reply_markup=admin_kb())
        await callback.answer()
    else:
        await callback.answer("⛔ Нет доступа", show_alert=True)

# ===== АДМИН-ОБРАБОТЧИКИ =====
@router.callback_query(F.data == "a_stats")
async def a_stats_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    total, prem, req, images, paid = get_stats()
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(tokens) FROM users")
        total_tokens = cursor.fetchone()[0] or 0
    await callback.message.edit_text(
        f"📊 **СТАТИСТИКА**\n\n"
        f"👥 Всего: {total}\n"
        f"💰 Всего токенов: {total_tokens}\n"
        f"📝 Запросов: {req}\n"
        f"🖼️ Картинок: {images}",
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
        cursor.execute("SELECT user_id, username, tokens, is_blocked FROM users ORDER BY tokens DESC LIMIT 20")
        users = cursor.fetchall()
    if not users:
        text = "👥 Нет пользователей"
    else:
        text = "👥 **Пользователи**\n\n"
        for u in users:
            status_text = "⛔" if u['is_blocked'] == 1 else "✅"
            name = u['username'] if u['username'] and u['username'] != str(u['user_id']) else "Без имени"
            text += f"{status_text} **{name}** (ID: {u['user_id']})\n"
            text += f"   🪙 {u['tokens']} токенов\n\n"
    await callback.message.edit_text(text[:4000], reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_broadcast")
async def a_broadcast_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    user_pages[callback.from_user.id] = {"state": "waiting_broadcast"}
    await callback.message.edit_text("📢 **Рассылка**\n\nВведите текст.\n\n⏹ /cancel", reply_markup=admin_kb())
    await callback.answer()

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
        await callback.answer("✅ Разблокирован", show_alert=True)
    else:
        block_user(user_id)
        await callback.answer("⛔ Заблокирован", show_alert=True)
    do_backup()
    await a_block_cb(callback)

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
        await callback.message.edit_text("📭 Нет обращений.", reply_markup=admin_kb())
        await callback.answer()
        return
    text = "📩 **Обращения**\n\n"
    for msg in messages:
        status = "🆕" if msg['status'] == "new" else "✅"
        name = msg['username'] if msg['username'] and msg['username'] != str(msg['user_id']) else str(msg['user_id'])
        text += f"{status} {msg['user_id']} — {name}\n"
        text += f"📝 {msg['text'][:50]}{'...' if len(msg['text']) > 50 else ''}\n"
        text += f"🕐 {msg['date'][:16]}\n\n"
    await callback.message.edit_text(text[:4000], reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_backup")
async def a_backup_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    await callback.message.edit_text("⏳ Бэкап...")
    result = GitHubBackup().backup_db()
    await callback.message.edit_text("✅ Бэкап создан!" if result else "❌ Ошибка", reply_markup=admin_kb())
    await callback.answer()

async def handle_admin_input(message: types.Message):
    user_id = message.from_user.id
    state = user_pages.get(user_id, {})
    if message.text == "/cancel":
        user_pages.pop(user_id, None)
        await message.answer("✅ Отменено", reply_markup=admin_kb())
        return
    
    if state.get("state") == "waiting_broadcast":
        if not message.text or not message.text.strip():
            await message.answer("❌ Текст не может быть пустым!", reply_markup=admin_kb())
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

