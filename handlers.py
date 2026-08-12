from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, BufferedInputFile
from database.db import *
from ai.client import solve_problem
from backup import GitHubBackup
import logging, secrets, os, requests, asyncio, json
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from openai import OpenAI

router = Router()
logger = logging.getLogger(__name__)
user_modes = {}
user_pages = {}
ADMIN_CODE = "30121979"
API_KEY = os.getenv('OPENAI_API_KEY')
PROVIDER_TOKEN = os.getenv('PROVIDER_TOKEN', '')
PROMPT_MODEL = "gpt-4.1-nano"

client = OpenAI(
    api_key=API_KEY,
    base_url='https://openai.bothub.chat/v1'
)

# ===== МОДЕЛИ ДЛЯ КАРТИНОК (ТОЛЬКО 2) =====
IMAGE_MODELS = {
    "flux": {
        "name": "🖼️ Flux Schnell",
        "price": 10,
        "api_model": "flux-schnell",
        "type": "replicate",
        "description": "Быстрая, базовая"
    },
    "flux_2_max": {
        "name": "🔥 Flux-2-Max",
        "price": 100,
        "api_model": "flux-2-max",
        "type": "replicate",
        "description": "⭐ ТОПОВОЕ КАЧЕСТВО"
    }
}

model_stats = {
    "flux": 0,
    "flux_2_max": 0
}

user_model = {}

def get_tokens(user_id):
    user = get_user(user_id)
    if not user:
        return 0
    try:
        return user['tokens'] if user['tokens'] else 0
    except:
        return 0

def add_tokens(user_id, amount):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET tokens = tokens + ? WHERE user_id = ?", (amount, user_id))

def spend_tokens(user_id, amount):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT tokens FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row and row[0] >= amount:
            cursor.execute("UPDATE users SET tokens = tokens - ? WHERE user_id = ?", (amount, user_id))
            return True
        return False

def has_trial(user_id):
    user = get_user(user_id)
    if not user:
        return False
    try:
        trial_start = user['trial_start'] if user['trial_start'] else None
        if not trial_start:
            return False
        start_date = datetime.fromisoformat(trial_start)
        return (datetime.now() - start_date).days < 3
    except:
        return False

def activate_trial(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET trial_start = ?, tokens = tokens + 20 WHERE user_id = ?", 
                      (datetime.now().isoformat(), user_id))

def get_trial_remaining(user_id):
    user = get_user(user_id)
    if not user:
        return 0
    try:
        trial_start = user['trial_start'] if user['trial_start'] else None
        if not trial_start:
            return 0
        start_date = datetime.fromisoformat(trial_start)
        days_passed = (datetime.now() - start_date).days
        return max(0, 3 - days_passed)
    except:
        return 0

def get_text_requests(user_id):
    user = get_user(user_id)
    if not user:
        return 0, 10
    try:
        used = user['text_requests'] if user['text_requests'] else 0
        max_req = user['max_text_requests'] if user['max_text_requests'] else 10
        return used, max_req
    except:
        return 0, 10

def reset_text_requests_if_needed(user_id):
    user = get_user(user_id)
    if not user:
        return
    try:
        last_reset = user['text_requests_reset'] if user['text_requests_reset'] else None
        if not last_reset:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET text_requests = 0, text_requests_reset = ? WHERE user_id = ?", 
                              (datetime.now().isoformat(), user_id))
            return
        last_date = datetime.fromisoformat(last_reset)
        if last_date.date() < datetime.now().date():
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET text_requests = 0, text_requests_reset = ? WHERE user_id = ?", 
                              (datetime.now().isoformat(), user_id))
    except:
        pass

def add_text_request(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET text_requests = text_requests + 1 WHERE user_id = ?", (user_id,))

def can_request_text(user_id):
    reset_text_requests_if_needed(user_id)
    used, max_req = get_text_requests(user_id)
    return used < max_req, max_req - used

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
    except:
        return None

def force_create_user(user_id, username=None):
    try:
        user = get_user(user_id)
        if user:
            return user
        result = create_user(user_id, username or str(user_id))
        if result:
            return get_user(user_id)
        return None
    except:
        return None

def do_backup():
    try:
        GitHubBackup().backup_db()
    except:
        pass

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

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧠 Текст", callback_data="mode_text"), InlineKeyboardButton(text="🖼️ Картинка", callback_data="mode_image")],
        [InlineKeyboardButton(text="🎨 Выбрать модель", callback_data="select_model")],
        [InlineKeyboardButton(text="✨ Купить токены", callback_data="buy_tokens"), InlineKeyboardButton(text="📊 Баланс", callback_data="balance")],
        [InlineKeyboardButton(text="🎁 Промокод", callback_data="promo_use"), InlineKeyboardButton(text="👥 Рефералы", callback_data="referral")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"), InlineKeyboardButton(text="📩 Поддержка", callback_data="contact_admin")],
        [InlineKeyboardButton(text="🛡️ Админ", callback_data="admin_panel"), InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ])

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="a_stats"), InlineKeyboardButton(text="📈 Модели", callback_data="a_model_stats")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="a_users"), InlineKeyboardButton(text="⭐ Раздать токены", callback_data="a_give_tokens")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="a_broadcast"), InlineKeyboardButton(text="🚫 Блокировка", callback_data="a_block")],
        [InlineKeyboardButton(text="💾 Бэкап", callback_data="a_backup"), InlineKeyboardButton(text="📩 Обращения", callback_data="a_messages")],
        [InlineKeyboardButton(text="📤 Выгрузить БД", callback_data="a_export_db"), InlineKeyboardButton(text="📥 Восстановить из GitHub", callback_data="a_restore_github")],
        [InlineKeyboardButton(text="💰 Цены", callback_data="a_edit_prices"), InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

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
            if success and "вы получили" in msg:
                add_tokens(referrer_id, 20)
                await message.answer("👤 Реферал +20 токенов!")
    
    if not has_trial(user_id) and get_tokens(user_id) == 0:
        activate_trial(user_id)
        trial_text = "🎁 Тебе подарок! 20 токенов (2 картинки) бесплатно на 3 дня!"
    else:
        trial_text = ""
    
    tokens = get_tokens(user_id)
    used, max_req = get_text_requests(user_id)
    text = (
        f"🤖 **Vertex AI**\n\n"
        f"💰 Токенов: {tokens}\n"
        f"🖼️ 10 токенов = 1 картинка\n"
        f"📝 Текст: {used}/{max_req} запросов сегодня\n\n"
        f"✨ Покупай токены или просто напиши вопрос!\n"
        f"{trial_text}\n\n"
        f"📌 Нажми «Текст» или «Картинка»!"
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
    used, max_req = get_text_requests(user_id)
    trial = get_trial_remaining(user_id)
    text = f"💰 **Баланс**\n\n"
    text += f"🪙 Токенов: {tokens}\n"
    text += f"🖼️ Хватит на: {tokens // 10} картинок\n"
    text += f"📝 Текст: {used}/{max_req} запросов сегодня\n"
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
        f"🆔 ID: {user_id}\n"
        f"👤 Имя: {message.from_user.username or 'без имени'}\n"
        f"💰 Токенов: {tokens}\n"
        f"🖼️ Картинок: {tokens // 10}\n"
    )
    await message.answer(text, reply_markup=main_menu())

@router.message(Command("help"))
async def help_cmd(message: types.Message):
    text = (
        "❓ **Помощь**\n\n"
        "🧠 Текст — просто напиши вопрос (10/день)\n"
        "🖼️ Картинка — от 10 токенов (выбери модель)\n"
        "🎨 Выбрать модель — измени модель для картинок\n"
        "✨ Купить токены — пополнить баланс\n"
        "📊 Баланс — проверить токены\n"
        "🎁 Промокод — активировать бонус\n"
        "👥 Рефералы — приглашай друзей (+20 токенов)\n\n"
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
    
    if state.get("state") in ["waiting_broadcast", "waiting_block_user", "waiting_contact", "waiting_give_tokens", "waiting_price"]:
        await handle_admin_input(message)
        return
    
    mode = user_modes.get(user_id, "text")
    if mode == "image":
        await generate_image(message)
    else:
        await generate_text(message)

async def generate_text(message: types.Message):
    user_id = message.from_user.id
    if not can_request_text(user_id):
        await message.answer("🔒 Лимит текстовых запросов исчерпан! Завтра будет новый день.", reply_markup=main_menu())
        return
    
    status_msg = await message.answer("🤔 Думаю...")
    try:
        answer = solve_problem(message.text, "chat", False)
        add_text_request(user_id)
        do_backup()
        used, max_req = get_text_requests(user_id)
        await status_msg.edit_text(f"🧠 {answer}\n\n📝 Осталось запросов: {max_req - used}/{max_req}")
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def generate_image(message: types.Message):
    user_id = message.from_user.id
    user = force_create_user(user_id, message.from_user.username or "")
    if not user:
        await message.answer("❌ Ошибка!", reply_markup=main_menu())
        return
    
    model_key = user_model.get(user_id, "flux")
    model_config = IMAGE_MODELS.get(model_key, IMAGE_MODELS["flux"])
    
    tokens = get_tokens(user_id)
    if tokens < model_config["price"]:
        trial = get_trial_remaining(user_id)
        if trial > 0:
            await message.answer(
                f"⚠️ У тебя осталось {tokens} токенов.\n"
                f"🎁 Пробный период: {trial} дней\n"
                f"Для этой модели нужно {model_config['price']} токенов.",
                reply_markup=main_menu()
            )
            return
        await message.answer(
            f"❌ Недостаточно токенов!\n"
            f"Нужно: {model_config['price']} токенов\n"
            f"У тебя: {tokens}\n\n"
            "✨ Купи токены или выбери более дешёвую модель.",
            reply_markup=main_menu()
        )
        return
    
    if not API_KEY:
        return await message.answer("❌ API ключ не настроен")
    
    if model_key in model_stats:
        model_stats[model_key] += 1
    
    status_msg = await message.answer(f"🎨 Генерирую картинку ({model_config['name']})...")
    try:
        user_prompt = message.text
        
        prompt_resp = requests.post(
            "https://openai.bothub.chat/v1/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={"model": PROMPT_MODEL, "messages": [{"role": "system", "content": "Create detailed English prompt for image generation. Only the prompt!"}, {"role": "user", "content": f"Prompt for: {user_prompt}"}], "max_tokens": 200},
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
        
        img_data = None
        
        if model_config["type"] == "openai":
            # OpenAI модели (пока не используются)
            await status_msg.edit_text("❌ OpenAI модели временно отключены")
            return
            try:
                params = {
                    'model': model_config["api_model"],
                    'prompt': enhanced,
                    'n': 1,
                    'size': '1024x1024',
                }
                req = client.images.generate(**params)
                # Получаем URL из ответа
                if hasattr(req, 'data') and len(req.data) > 0:
                    image_url = req.data[0].url
                    if image_url:
                        img_data_response = requests.get(image_url, timeout=30)
                        if img_data_response.status_code == 200 and len(img_data_response.content) > 1000:
                            img_data = img_data_response.content
                else:
                    # fallback: через json
                    resp_json = json.loads(req.model_dump_json())
                    if 'data' in resp_json and len(resp_json['data']) > 0:
                        image_url = resp_json['data'][0]['url']
                        if image_url:
                            img_data_response = requests.get(image_url, timeout=30)
                            if img_data_response.status_code == 200 and len(img_data_response.content) > 1000:
                                img_data = img_data_response.content
            except Exception as e:
                logger.error(f"Ошибка: {e}")
                await status_msg.edit_text(f"❌ Ошибка генерации: {str(e)[:100]}")
                return
        else:
            img_resp = requests.post(
                "https://bothub.chat/api/v2/replicate/v1/images/generations",
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json={"model": model_config["api_model"], "input": {"prompt": enhanced, "aspect_ratio": "1:1", "output_format": "webp"}, "bothub": {"include_usage": True, "return_base64": False}},
                timeout=120
            )
            if img_resp.status_code == 200:
                result = img_resp.json()
                img_url = result.get('url')
                if isinstance(img_url, list):
                    img_url = img_url[0]
                if img_url:
                    img_data_response = requests.get(img_url, timeout=30)
                    if img_data_response.status_code == 200 and len(img_data_response.content) > 1000:
                        img_data = img_data_response.content
        
        if img_data:
            await status_msg.edit_text("🎨 100% ✅")
            await asyncio.sleep(0.2)
            
            watermarked = add_watermark(img_data)
            if watermarked:
                img_data = watermarked
            
            spend_tokens(user_id, model_config["price"])
            do_backup()
            
            new_tokens = get_tokens(user_id)
            await message.answer_photo(
                BufferedInputFile(file=img_data.getvalue() if hasattr(img_data, 'getvalue') else img_data, filename="image.png"),
                caption=f"🖼️ **Твоя картинка**\n"
                        f"📝 {user_prompt[:50]}...\n"
                        f"🤖 Модель: {model_config['name']}\n"
                        f"💰 Потрачено: {model_config['price']} токенов\n"
                        f"🪙 Осталось: {new_tokens} токенов"
            )
            await status_msg.delete()
            return
        
        await status_msg.edit_text("❌ Не удалось получить картинку")
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

@router.callback_query(F.data.in_(["mode_text", "mode_image"]))
async def set_mode(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    mode = callback.data.replace("mode_", "")
    user_modes[user_id] = mode
    mode_name = "🧠 Текст" if mode == "text" else "🖼️ Картинка"
    await callback.answer(f"✅ Режим: {mode_name}", show_alert=True)
    await callback.message.edit_text(
        f"✅ Режим **{mode_name}**\n\n"
        "Просто напиши свой запрос!",
        reply_markup=main_menu()
    )

@router.callback_query(F.data == "select_model")
async def select_model_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for key, model in IMAGE_MODELS.items():
        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{model['name']} — {model['price']} токенов",
                callback_data=f"model_{key}"
            )
        ])
    kb.inline_keyboard.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")
    ])
    
    text = "🧠 **Выбери модель для генерации картинок:**\n\n"
    for key, model in IMAGE_MODELS.items():
        text += f"{model['name']} — {model['price']} токенов\n"
        text += f"   {model['description']}\n\n"
    text += "Выбери модель ниже 👇"
    
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("model_"))
async def set_model_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    model_key = callback.data.replace("model_", "")
    
    if model_key not in IMAGE_MODELS:
        await callback.answer("❌ Модель не найдена", show_alert=True)
        return
    
    user_model[user_id] = model_key
    model = IMAGE_MODELS[model_key]
    
    await callback.answer(f"✅ Выбрана модель: {model['name']}", show_alert=True)
    await callback.message.edit_text(
        f"✅ **Выбрана модель:** {model['name']}\n"
        f"💰 Стоимость: {model['price']} токенов за картинку\n"
        f"📝 {model['description']}\n\n"
        "Теперь все картинки будут генерироваться через эту модель.\n"
        "Напиши описание и получи результат!",
        reply_markup=main_menu()
    )

@router.callback_query(F.data == "balance")
async def balance_cb(callback: types.CallbackQuery):
    await balance_cmd(callback.message)
    await callback.answer()

@router.callback_query(F.data == "profile")
async def profile_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = force_create_user(user_id, callback.from_user.username or "")
    if not user:
        await callback.answer("❌ Ошибка!", show_alert=True)
        return
    tokens = get_tokens(user_id)
    username = callback.from_user.username or "без имени"
    text = (
        f"👤 **Мой профиль**\n\n"
        f"🆔 ID: {user_id}\n"
        f"👤 Имя: {username}\n"
        f"💰 Токенов: {tokens}\n"
        f"🖼️ Картинок: {tokens // 10}\n"
    )
    try:
        await callback.message.edit_text(text, reply_markup=main_menu())
    except:
        await callback.message.answer(text, reply_markup=main_menu())
    await callback.answer()

@router.callback_query(F.data == "referral")
async def referral_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = force_create_user(user_id, callback.from_user.username or "")
    if not user:
        await callback.answer("❌ Ошибка!", show_alert=True)
        return
    count = get_referral_count(user_id)
    link = f"https://t.me/Vertex1bot?start={user_id}"
    text = (
        "👥 **Рефералы**\n\n"
        f"👤 Приглашено: {count}\n"
        f"🎁 Бонус: +20 токенов за друга\n\n"
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
    used, max_req = get_text_requests(user_id)
    text = (
        f"🤖 **Vertex AI**\n\n"
        f"💰 Токенов: {tokens}\n"
        f"🖼️ 10 токенов = 1 картинка\n"
        f"📝 Текст: {used}/{max_req} запросов сегодня\n\n"
        f"Напиши вопрос или выбери режим!"
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

@router.callback_query(F.data == "a_stats")
async def a_stats_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    total, prem, req, images, paid = get_stats()
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(tokens) FROM users WHERE user_id != 8676871187")
        total_tokens = cursor.fetchone()[0] or 0
    await callback.message.edit_text(
        f"📊 **СТАТИСТИКА**\n\n"
        f"👥 Всего: {total - 1}\n"
        f"💰 Всего токенов: {total_tokens}\n"
        f"📝 Запросов: {req}\n"
        f"🖼️ Картинок: {images}",
        reply_markup=admin_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "a_model_stats")
async def a_model_stats_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    total = sum(model_stats.values())
    text = "📈 **СТАТИСТИКА МОДЕЛЕЙ**\n\n"
    text += f"Всего генераций: {total}\n\n"
    
    sorted_stats = sorted(model_stats.items(), key=lambda x: x[1], reverse=True)
    
    for key, count in sorted_stats:
        if count > 0:
            model = IMAGE_MODELS[key]
            percent = round(count / total * 100, 1) if total > 0 else 0
            text += f"{model['name']}\n"
            text += f"   🔹 {count} генераций ({percent}%)\n\n"
    
    if total == 0:
        text += "❌ Пока нет статистики.\n"
        text += "Пользователи ещё не генерировали картинки."
    
    await callback.message.edit_text(text, reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_users")
async def a_users_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, tokens, is_blocked FROM users WHERE user_id != 8676871187 ORDER BY tokens DESC LIMIT 20")
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

@router.callback_query(F.data == "a_give_tokens")
async def a_give_tokens_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    user_pages[callback.from_user.id] = {"state": "waiting_give_tokens"}
    await callback.message.edit_text(
        "⭐ **Раздать токены**\n\n"
        "Введите в формате:\n"
        "`ID пользователя | количество токенов`\n\n"
        "Пример: `123456789 | 50`\n\n"
        "Или напиши `всем | 10` чтобы раздать всем по 10 токенов\n\n"
        "⏹ /cancel",
        reply_markup=admin_kb()
    )
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
        cursor.execute("SELECT user_id, username, is_blocked FROM users WHERE user_id != 8676871187 ORDER BY user_id LIMIT 20")
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

@router.callback_query(F.data == "a_export_db")
async def export_db_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    import os
    db_path = "data/repsolver.db"
    if not os.path.exists(db_path):
        await callback.message.edit_text("❌ Файл базы данных не найден!", reply_markup=admin_kb())
        await callback.answer()
        return
    try:
        await callback.message.delete()
        await callback.message.answer_document(
            BufferedInputFile(open(db_path, "rb").read(), filename="repsolver.db"),
            caption="📁 **База данных**\n\nСкачана в формате SQLite",
            reply_markup=admin_kb()
        )
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {str(e)[:100]}", reply_markup=admin_kb())
    await callback.answer()

def get_backup_list():
    import requests
    token = os.getenv('GITHUB_TOKEN')
    repo = os.getenv('GITHUB_BACKUP_REPO')
    if not token or not repo:
        return []
    headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
    url = f'https://api.github.com/repos/{repo}/contents/backups'
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return []
    files = [f for f in resp.json() if f['name'].endswith('.db')]
    files.sort(key=lambda x: x['name'], reverse=True)
    return files

def restore_backup_from_github(filename):
    import requests
    import os
    token = os.getenv('GITHUB_TOKEN')
    repo = os.getenv('GITHUB_BACKUP_REPO')
    if not token or not repo:
        return False
    headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
    url = f'https://api.github.com/repos/{repo}/contents/backups/{filename}'
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return False
    file_url = resp.json()['download_url']
    resp = requests.get(file_url)
    if resp.status_code != 200:
        return False
    os.makedirs('data', exist_ok=True)
    with open('data/repsolver.db', 'wb') as f:
        f.write(resp.content)
    return True

@router.callback_query(F.data == "a_restore_github")
async def restore_github_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    files = get_backup_list()
    if not files:
        await callback.message.edit_text(
            "❌ Нет бэкапов на GitHub!\n\n"
            "Сначала создайте бэкап в админке (кнопка 💾 Бэкап).",
            reply_markup=admin_kb()
        )
        await callback.answer()
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for f in files[:20]:
        name = f['name']
        size_kb = round(f['size'] / 1024, 1)
        label = f"📄 {name[:20]}... ({size_kb} KB)" if len(name) > 20 else f"📄 {name} ({size_kb} KB)"
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=label, callback_data=f"restore_backup_{name}")
        ])
    kb.inline_keyboard.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")
    ])
    await callback.message.edit_text(
        "📥 **Восстановление из GitHub**\n\n"
        "Выберите бэкап для восстановления:\n"
        f"📦 Всего: {len(files)} бэкапов",
        reply_markup=kb
    )
    await callback.answer()

@router.callback_query(F.data.startswith("restore_backup_"))
async def restore_backup_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    filename = callback.data.replace("restore_backup_", "")
    await callback.message.edit_text(
        f"⏳ Восстанавливаю бэкап: `{filename}`...",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Отмена", callback_data="a_restore_github")]
        ])
    )
    success = restore_backup_from_github(filename)
    if success:
        await callback.message.edit_text(
            f"✅ **Бэкап восстановлен!**\n\n"
            f"📄 Файл: `{filename}`\n"
            f"🔄 Бот перезапущен.",
            reply_markup=admin_kb()
        )
    else:
        await callback.message.edit_text(
            f"❌ **Ошибка восстановления!**\n\n"
            f"📄 Файл: `{filename}`\n"
            f"Попробуйте другой бэкап.",
            reply_markup=admin_kb()
        )
    await callback.answer()



# ===== УПРАВЛЕНИЕ ЦЕНАМИ =====
@router.callback_query(F.data == "a_edit_prices")
async def a_edit_prices_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for key, model in IMAGE_MODELS.items():
        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{model['name']} — {model['price']} токенов",
                callback_data=f"edit_price_{key}"
            )
        ])
    kb.inline_keyboard.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")
    ])
    
    await callback.message.edit_text(
        "💰 **Управление ценами**\n\n"
        "Выбери модель для изменения цены:",
        reply_markup=kb
    )
    await callback.answer()

@router.callback_query(F.data.startswith("edit_price_"))
async def edit_price_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    model_key = callback.data.replace("edit_price_", "")
    model = IMAGE_MODELS[model_key]
    user_pages[callback.from_user.id] = {"state": "waiting_price", "model": model_key}
    
    await callback.message.edit_text(
        f"💰 **Изменение цены**\n\n"
        f"Модель: {model['name']}\n"
        f"Текущая цена: {model['price']} токенов\n\n"
        f"Введи **новую цену** в токенах:\n"
        f"(например: `15`)\n\n"
        f"⏹ /cancel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="a_edit_prices")]
        ])
    )
    await callback.answer()

async def handle_admin_input(message: types.Message):
    user_id = message.from_user.id
    state = user_pages.get(user_id, {})
    if message.text == "/cancel":
        user_pages.pop(user_id, None)
        await message.answer("✅ Отменено", reply_markup=admin_kb())
        return
    
    if state.get("state") == "waiting_price":
        try:
            new_price = int(message.text.strip())
            if new_price < 1:
                await message.answer("❌ Цена должна быть больше 0!", reply_markup=admin_kb())
                return
            model_key = state.get("model")
            if model_key and model_key in IMAGE_MODELS:
                IMAGE_MODELS[model_key]["price"] = new_price
                await message.answer(
                    f"✅ Цена для {IMAGE_MODELS[model_key]['name']} обновлена!\n"
                    f"💰 Новая цена: {new_price} токенов",
                    reply_markup=admin_kb()
                )
            else:
                await message.answer("❌ Модель не найдена", reply_markup=admin_kb())
        except ValueError:
            await message.answer("❌ Введите число!", reply_markup=admin_kb())
        user_pages.pop(user_id, None)
        return
    
    if state.get("state") == "waiting_give_tokens":
        try:
            text = message.text.strip()
            if text.startswith("всем"):
                parts = text.split("|")
                if len(parts) < 2:
                    await message.answer("❌ Формат: всем | количество")
                    return
                amount = int(parts[1].strip())
                from database.db import get_db
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT user_id FROM users WHERE is_blocked = 0 AND user_id != 8676871187")
                    users = cursor.fetchall()
                count = 0
                for u in users:
                    add_tokens(u['user_id'], amount)
                    count += 1
                await message.answer(f"✅ Раздано {amount} токенов {count} пользователям!", reply_markup=admin_kb())
            else:
                parts = text.split("|")
                if len(parts) < 2:
                    await message.answer("❌ Формат: ID | количество")
                    return
                target_id = int(parts[0].strip())
                amount = int(parts[1].strip())
                if target_id == 8676871187:
                    await message.answer("❌ Нельзя выдавать токены боту!", reply_markup=admin_kb())
                    return
                add_tokens(target_id, amount)
                await message.answer(f"✅ Пользователю {target_id} начислено {amount} токенов!", reply_markup=admin_kb())
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}", reply_markup=admin_kb())
        user_pages.pop(user_id, None)
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
            cursor.execute("SELECT user_id FROM users WHERE is_blocked = 0 AND user_id != 8676871187")
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

