from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, BufferedInputFile
from aiogram.exceptions import TelegramBadRequest
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

# ===== СОСТОЯНИЯ =====
user_modes = {}
user_pages = {}
user_model = {}

# ===== КОНСТАНТЫ =====
ADMIN_CODE = "30121979"
API_KEY = os.getenv('OPENAI_API_KEY')
PROVIDER_TOKEN = os.getenv('PROVIDER_TOKEN', '')
PROMPT_MODEL = "gpt-4.1-nano"
ADMIN_ID = int(os.getenv('ADMIN_ID', 6957852385))

# ===== МОДЕЛИ ДЛЯ КАРТИНОК =====
IMAGE_MODELS = {
    "flux": {
        "name": "🖼️ Flux Schnell",
        "price": 10,
        "api_model": "flux-schnell",
        "type": "replicate",
        "description": "⚡ Быстрая, базовая"
    },
    "flux_2_max": {
        "name": "🔥 Flux-2-Max",
        "price": 100,
        "api_model": "flux-2-max",
        "type": "replicate",
        "description": "⭐ ТОПОВОЕ КАЧЕСТВО"
    }
}

model_stats = {"flux": 0, "flux_2_max": 0}

# ===== КЛИЕНТ =====
client = OpenAI(
    api_key=API_KEY,
    base_url='https://openai.bothub.chat/v1'
)


# ============================================================================
# =========================== БЕЗОПАСНЫЕ ФУНКЦИИ ===========================
# ============================================================================

async def safe_answer(callback: types.CallbackQuery, text: str = None, show_alert: bool = False):
    """Безопасный ответ на callback — никогда не падает"""
    try:
        if text:
            await callback.answer(text, show_alert=show_alert)
        else:
            await callback.answer()
    except TelegramBadRequest:
        pass
    except Exception:
        pass


# ============================================================================
# =========================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =======================
# ============================================================================

def get_tokens(user_id):
    user = get_user(user_id)
    if not user:
        return 0
    return user['tokens'] if user['tokens'] else 0

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

def is_admin(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
        return cursor.fetchone() is not None

def add_admin(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)",
                      (user_id, datetime.now().isoformat()))

def do_backup():
    try:
        GitHubBackup().backup_db()
    except:
        pass

def force_create_user(user_id, username=None):
    try:
        user = get_user(user_id)
        if user:
            return user
        result = create_user(user_id, username or str(user_id))
        if result:
            init_user_memory(user_id)
            return get_user(user_id)
        return None
    except:
        return None

def detect_edit_type(text):
    text_lower = text.lower()
    if any(w in text_lower for w in ['цвет', 'чёрн', 'бел', 'красн', 'син', 'зелён', 'жёлт', 'оранж', 'фиолет', 'розов', 'голуб']):
        return 'color'
    elif any(w in text_lower for w in ['добав', 'нарису', 'постав']):
        return 'add'
    elif any(w in text_lower for w in ['убери', 'удал', 'убр', 'убрат']):
        return 'remove'
    elif any(w in text_lower for w in ['фон', 'задн', 'обои']):
        return 'background'
    elif any(w in text_lower for w in ['стиль', 'в стиле', 'как']):
        return 'style'
    else:
        return 'general'

def build_edit_prompt(base_prompt, edit_text):
    edit_type = detect_edit_type(edit_text)
    if edit_type == 'color':
        return f"{base_prompt}, {edit_text}"
    elif edit_type == 'add':
        return f"{base_prompt}, {edit_text}"
    elif edit_type == 'remove':
        cleaned = edit_text.replace('убери', '').replace('удал', '').strip()
        return f"{base_prompt}, без {cleaned}"
    elif edit_type == 'background':
        cleaned = edit_text.replace('сделай фон', '').replace('фон', '').strip()
        return f"{base_prompt}, фон {cleaned}"
    else:
        return f"{base_prompt}, {edit_text}"

def get_edit_version(user_id, session_id):
    chain = get_image_chain_by_session(user_id, session_id)
    return len(chain)

def get_trial_remaining_text(user_id):
    days = get_trial_remaining(user_id)
    if days == 0:
        return "закончился"
    elif days == 1:
        return "1 день"
    elif days <= 4:
        return f"{days} дня"
    else:
        return f"{days} дней"

def get_user_name(user_id):
    memory = get_user_memory(user_id)
    if memory and memory.get('name'):
        return memory['name']
    return None

def get_user_style(user_id):
    memory = get_user_memory(user_id)
    if memory and memory.get('favorite_style'):
        return memory['favorite_style']
    return "Не выбран"


# ============================================================================
# ================================ КЛАВИАТУРЫ ================================
# ============================================================================

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧠 Текст", callback_data="mode_text"),
         InlineKeyboardButton(text="🖼️ Картинка", callback_data="mode_image")],
        [InlineKeyboardButton(text="🎨 Выбрать модель", callback_data="select_model")],
        [InlineKeyboardButton(text="✨ Купить токены", callback_data="buy_tokens"),
         InlineKeyboardButton(text="📊 Баланс", callback_data="balance")],
        [InlineKeyboardButton(text="🎁 Промокод", callback_data="promo_use"),
         InlineKeyboardButton(text="👥 Рефералы", callback_data="referral")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="📩 Поддержка", callback_data="contact_admin")],
        [InlineKeyboardButton(text="🛡️ Админ", callback_data="admin_panel"),
         InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ])

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="a_stats"),
         InlineKeyboardButton(text="📈 Модели", callback_data="a_model_stats")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="a_users"),
         InlineKeyboardButton(text="⭐ Раздать токены", callback_data="a_give_tokens")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="a_broadcast"),
         InlineKeyboardButton(text="🚫 Блокировка", callback_data="a_block")],
        [InlineKeyboardButton(text="💾 Бэкап", callback_data="a_backup"),
         InlineKeyboardButton(text="📩 Обращения", callback_data="a_messages")],
        [InlineKeyboardButton(text="📤 Выгрузить БД", callback_data="a_export_db"),
         InlineKeyboardButton(text="📥 Восстановить из GitHub", callback_data="a_restore_github")],
        [InlineKeyboardButton(text="💰 Цены", callback_data="a_edit_prices"),
         InlineKeyboardButton(text="🎫 Промокоды", callback_data="a_promocodes")],
        [InlineKeyboardButton(text="⭐ Баланс Stars", callback_data="a_stars_balance")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

def image_action_buttons(image_id, session_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Поправить", callback_data=f"edit_{image_id}"),
            InlineKeyboardButton(text="🔄 Ещё вариант", callback_data=f"variation_{image_id}")
        ],
        [
            InlineKeyboardButton(text="📊 История правок", callback_data=f"history_{session_id}"),
            InlineKeyboardButton(text="🗑️ Закрыть сессию", callback_data=f"close_{session_id}")
        ],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
    ])

def edit_in_progress_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏹ Отменить правку", callback_data="cancel_edit")]
    ])


# ============================================================================
# ============================== КОМАНДЫ ====================================
# ============================================================================

@router.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    user = force_create_user(user_id, username)
    if not user:
        await message.answer("❌ Ошибка регистрации.")
        return

    memory = get_user_memory(user_id)
    if not memory or not memory.get('name'):
        user_pages[user_id] = {"state": "waiting_name"}
        await message.answer(
            "👋 Привет! Я — **Vertex AI** — твой личный ассистент с памятью.\n\n"
            "✨ Я умею:\n"
            "• 🖼️ Создавать картинки\n"
            "• 🧠 Отвечать на вопросы\n"
            "• ✏️ Редактировать картинки по шагам\n"
            "• 🧠 Запоминать твои предпочтения\n\n"
            "Как мне тебя называть?\n"
            "Напиши своё имя:"
        )
        return

    args = message.text.split() if message.text else []
    if len(args) > 1 and args[1].isdigit():
        referrer_id = int(args[1])
        if referrer_id != user_id:
            success, msg = add_referral(referrer_id, user_id)
            if success:
                await message.answer(msg)

    if not has_trial(user_id) and get_tokens(user_id) == 0:
        activate_trial(user_id)
        trial_text = "🎁 Тебе подарок! 20 токенов (2 картинки) бесплатно на 3 дня!"
    else:
        trial_text = ""

    tokens = get_tokens(user_id)
    used, max_req = get_text_requests(user_id)
    name = get_user_name(user_id) or "друг"
    style = get_user_style(user_id)

    text = (
        f"✨ **Vertex AI**\n\n"
        f"👋 Привет, {name}!\n"
        f"🎨 Твой стиль: {style}\n\n"
        f"💰 Токенов: {tokens}\n"
        f"🖼️ 10 токенов = 1 картинка\n"
        f"✏️ 5 токенов = 1 правка\n"
        f"📝 Текст: {used}/{max_req} запросов сегодня\n\n"
        f"{trial_text}\n\n"
        f"💬 Напиши вопрос или выбери режим ниже:"
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
    trial = get_trial_remaining_text(user_id)
    text = (
        f"💰 **Баланс**\n\n"
        f"🪙 Токенов: {tokens}\n"
        f"🖼️ Хватит на: {tokens // 10} картинок\n"
        f"✏️ Хватит на: {tokens // 5} правок\n"
        f"📝 Текст: {used}/{max_req} запросов сегодня\n"
        f"🎁 Пробный период: {trial}"
    )
    await message.answer(text, reply_markup=main_menu())

@router.message(Command("profile"))
async def profile_cmd(message: types.Message):
    user_id = message.from_user.id
    user = force_create_user(user_id, message.from_user.username or "")
    if not user:
        await message.answer("❌ Ошибка!", reply_markup=main_menu())
        return

    tokens = get_tokens(user_id)
    name = get_user_name(user_id) or "Не указано"
    style = get_user_style(user_id)
    memory = get_user_memory(user_id)
    context_count = len(json.loads(memory.get('context_history', '[]'))) if memory else 0

    text = (
        f"👤 **Мой профиль**\n\n"
        f"🆔 ID: {user_id}\n"
        f"👤 Имя: {name}\n"
        f"🎨 Любимый стиль: {style}\n"
        f"📝 История: {context_count} запросов\n"
        f"💰 Токенов: {tokens}\n"
        f"🖼️ Картинок: {tokens // 10}\n"
        f"✏️ Правок: {tokens // 5}"
    )
    await message.answer(text, reply_markup=main_menu())

@router.message(Command("help"))
async def help_cmd(message: types.Message):
    text = (
        "❓ **Помощь**\n\n"
        "🧠 **Текст** — просто напиши вопрос (10/день)\n"
        "🖼️ **Картинка** — от 10 токенов (выбери модель)\n"
        "✏️ **Правки** — измени детали картинки (5 токенов)\n"
        "🎨 **Выбрать модель** — измени модель для картинок\n"
        "✨ **Купить токены** — пополнить баланс\n"
        "📊 **Баланс** — проверить токены\n"
        "🎁 **Промокод** — активировать бонус\n"
        "👥 **Рефералы** — приглашай друзей (+20 токенов)\n\n"
        "📌 Команды:\n"
        "/start — меню\n"
        "/balance — баланс\n"
        "/profile — профиль\n"
        "/help — помощь\n"
        "/clear — очистить память"
    )
    await message.answer(text, reply_markup=main_menu())

@router.message(Command("clear"))
async def clear_memory_cmd(message: types.Message):
    user_id = message.from_user.id
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_memory WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM images_history WHERE user_id = ?", (user_id,))
    init_user_memory(user_id)
    await message.answer("🧹 Память очищена! Я ничего не помню о тебе.", reply_markup=main_menu())

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


# ============================================================================
# ============================ ОБРАБОТКА СООБЩЕНИЙ =========================
# ============================================================================

@router.message(F.text)
async def handle_message(message: types.Message):
    if not message.text or message.text.startswith("/"):
        return

    user_id = message.from_user.id
    state = user_pages.get(user_id, {})

    if state.get("state") == "waiting_name":
        name = message.text.strip()
        set_user_name(user_id, name)
        user_pages.pop(user_id, None)
        await message.answer(f"✅ Отлично, {name}! Я запомнил тебя.")
        await start_cmd(message)
        return

    if state.get("state") == "waiting_promo_use":
        success, msg = use_promocode(message.text.upper(), user_id)
        await message.answer(msg, reply_markup=main_menu())
        user_pages.pop(user_id, None)
        return

    if state.get("state") in ["waiting_broadcast", "waiting_block_user", "waiting_contact",
                              "waiting_give_tokens", "waiting_price", "waiting_promo_code"]:
        await handle_admin_input(message)
        return

    if state.get("state") == "waiting_edit":
        await handle_edit(message)
        return

    mode = user_modes.get(user_id, "text")
    if mode == "image":
        await generate_image(message)
    else:
        await generate_text(message)


# ============================================================================
# =========================== ТЕКСТОВЫЙ ИИ ==================================
# ============================================================================

async def generate_text(message: types.Message):
    user_id = message.from_user.id
    if not can_request_text(user_id):
        await message.answer("🔒 Лимит текстовых запросов исчерпан! Завтра будет новый день.", reply_markup=main_menu())
        return

    status_msg = await message.answer("🤔 Думаю...")
    try:
        memory = get_user_memory(user_id)
        context = []
        if memory and memory.get('context_history'):
            try:
                history = json.loads(memory['context_history'])
                context = [h['prompt'] for h in history[-5:]]
            except:
                pass

        full_prompt = message.text
        if context:
            full_prompt = f"Контекст: {' | '.join(context)}\nВопрос: {message.text}"

        answer = solve_problem(full_prompt, "chat", False)
        add_text_request(user_id)
        do_backup()
        used, max_req = get_text_requests(user_id)

        add_to_context(user_id, message.text)

        await status_msg.edit_text(f"🧠 {answer}\n\n📝 Осталось запросов: {max_req - used}/{max_req}")
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")


# ============================================================================
# =========================== ГЕНЕРАЦИЯ КАРТИНОК ===========================
# ============================================================================

async def generate_image(message: types.Message, is_edit=False, edit_context=None):
    user_id = message.from_user.id
    user = force_create_user(user_id, message.from_user.username or "")
    if not user:
        await message.answer("❌ Ошибка!", reply_markup=main_menu())
        return

    model_key = user_model.get(user_id, "flux")
    model_config = IMAGE_MODELS.get(model_key, IMAGE_MODELS["flux"])

    price = model_config["price"] if not is_edit else 5

    tokens = get_tokens(user_id)
    if tokens < price:
        trial = get_trial_remaining(user_id)
        if trial > 0:
            await message.answer(
                f"⚠️ У тебя осталось {tokens} токенов.\n"
                f"🎁 Пробный период: {trial} дней\n"
                f"Нужно: {price} токенов.",
                reply_markup=main_menu()
            )
            return
        await message.answer(
            f"❌ Недостаточно токенов!\n"
            f"Нужно: {price} токенов\n"
            f"У тебя: {tokens}\n\n"
            "✨ Купи токены!",
            reply_markup=main_menu()
        )
        return

    if not API_KEY:
        return await message.answer("❌ API ключ не настроен")

    if model_key in model_stats:
        model_stats[model_key] += 1

    status_msg = await message.answer(f"🎨 {'Редактирую' if is_edit else 'Генерирую'} картинку ({model_config['name']})...")

    try:
        user_prompt = message.text

        if is_edit and edit_context:
            full_prompt = edit_context.get('full_prompt', user_prompt)
        else:
            full_prompt = user_prompt

        memory = get_user_memory(user_id)
        style = memory.get('favorite_style') if memory else None
        if style and not is_edit:
            full_prompt = f"{full_prompt}, в стиле {style}"

        prompt_resp = requests.post(
            "https://openai.bothub.chat/v1/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "model": PROMPT_MODEL,
                "messages": [
                    {"role": "system", "content": "Create detailed English prompt for image generation. Only the prompt!"},
                    {"role": "user", "content": f"Prompt for: {full_prompt}"}
                ],
                "max_tokens": 200
            },
            timeout=30
        )
        enhanced = user_prompt
        if prompt_resp.status_code == 200:
            enhanced = prompt_resp.json().get('choices', [{}])[0].get('message', {}).get('content', user_prompt).strip('"')

        for p in range(5, 101, 5):
            await asyncio.sleep(0.2)
            try:
                await status_msg.edit_text(f"🎨 {p}%")
            except:
                pass

        img_data = None

        img_resp = requests.post(
            "https://bothub.chat/api/v2/replicate/v1/images/generations",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "model": model_config["api_model"],
                "input": {
                    "prompt": enhanced,
                    "aspect_ratio": "1:1",
                    "output_format": "webp"
                },
                "bothub": {"include_usage": True, "return_base64": False}
            },
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
            watermarked = add_watermark(img_data)
            if watermarked:
                img_data = watermarked

            spend_tokens(user_id, price)
            do_backup()

            image_id, session_id = save_image_to_history(
                user_id=user_id,
                prompt=user_prompt,
                enhanced_prompt=enhanced,
                model=model_key,
                image_data=img_data.getvalue() if hasattr(img_data, 'getvalue') else img_data,
                previous_id=edit_context.get('image_id') if edit_context else None,
                session_id=edit_context.get('session_id') if edit_context else None,
                edit_type=edit_context.get('edit_type') if edit_context else None,
                edit_text=user_prompt if is_edit else None
            )

            add_to_context(user_id, user_prompt, image_id, edit_context.get('edit_type') if edit_context else None)

            new_tokens = get_tokens(user_id)
            caption = (
                f"🖼️ **Твоя картинка**\n"
                f"📝 {user_prompt[:50]}{'...' if len(user_prompt) > 50 else ''}\n"
                f"🤖 {model_config['name']}\n"
                f"💰 -{price} токенов | 🪙 {new_tokens} осталось\n"
            )
            if is_edit:
                caption += f"✏️ Версия: {get_edit_version(user_id, session_id)}"

            await message.answer_photo(
                BufferedInputFile(
                    file=img_data.getvalue() if hasattr(img_data, 'getvalue') else img_data,
                    filename="image.png"
                ),
                caption=caption,
                reply_markup=image_action_buttons(image_id, session_id)
            )
            await status_msg.delete()
            return

        await status_msg.edit_text("❌ Не удалось получить картинку")

    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")


# ============================================================================
# ============================ ✏️ ПРАВКИ КАРТИНОК ===========================
# ============================================================================

@router.callback_query(F.data.startswith("edit_"))
async def edit_image_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    image_id = int(callback.data.replace("edit_", ""))

    image = get_image_by_id(image_id)
    if not image:
        await safe_answer(callback, "❌ Картинка не найдена", show_alert=True)
        return

    chain = get_image_chain(user_id, image_id)
    full_prompt = " + ".join([img['prompt'] for img in chain])

    user_pages[user_id] = {
        "state": "waiting_edit",
        "image_id": image_id,
        "session_id": image['session_id'],
        "original_prompt": image['prompt'],
        "full_prompt": full_prompt
    }

    await callback.message.answer(
        f"✏️ **Редактирование картинки**\n\n"
        f"📝 Текущий запрос: `{full_prompt[:100]}{'...' if len(full_prompt) > 100 else ''}`\n\n"
        f"Напиши, что изменить:\n"
        f"• *сделай кота чёрным*\n"
        f"• *добавь шляпу*\n"
        f"• *сделай фон ночным*\n\n"
        f"💰 Стоимость правки: 5 токенов\n"
        f"⏹ /cancel",
        reply_markup=edit_in_progress_kb()
    )
    await safe_answer(callback)

@router.callback_query(F.data == "cancel_edit")
async def cancel_edit_callback(callback: types.CallbackQuery):
    user_pages.pop(callback.from_user.id, None)
    await callback.message.edit_text("✅ Правка отменена", reply_markup=main_menu())
    await safe_answer(callback)

async def handle_edit(message: types.Message):
    user_id = message.from_user.id
    state = user_pages.get(user_id, {})

    edit_text = message.text.strip()
    image_id = state.get("image_id")
    session_id = state.get("session_id")
    full_prompt = state.get("full_prompt", "")

    if not image_id or not session_id:
        await message.answer("❌ Ошибка: нет картинки для редактирования")
        return

    edit_type = detect_edit_type(edit_text)
    new_prompt = build_edit_prompt(full_prompt, edit_text)

    await generate_image(
        message,
        is_edit=True,
        edit_context={
            'image_id': image_id,
            'session_id': session_id,
            'edit_type': edit_type,
            'full_prompt': new_prompt
        }
    )

    user_pages.pop(user_id, None)


# ============================================================================
# ============================ ДРУГИЕ КОЛБЭКИ ==============================
# ============================================================================

@router.callback_query(F.data.startswith("variation_"))
async def variation_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    image_id = int(callback.data.replace("variation_", ""))
    image = get_image_by_id(image_id)
    if not image:
        await safe_answer(callback, "❌ Картинка не найдена", show_alert=True)
        return

    await callback.message.answer("🔄 Генерирую новый вариант...")
    await generate_image(
        callback.message,
        is_edit=False,
        edit_context={'full_prompt': image['prompt']}
    )
    await safe_answer(callback)

@router.callback_query(F.data.startswith("history_"))
async def history_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    session_id = callback.data.replace("history_", "")

    chain = get_image_chain_by_session(user_id, session_id)
    if not chain:
        await safe_answer(callback, "❌ Нет истории", show_alert=True)
        return

    text = "📊 **История правок**\n\n"
    for i, img in enumerate(chain, 1):
        text += f"{i}. {img['prompt'][:50]}\n"
        text += f"   ✏️ Версия: {i}\n\n"

    await callback.message.edit_text(text[:4000], reply_markup=main_menu())
    await safe_answer(callback)

@router.callback_query(F.data.startswith("close_"))
async def close_session_callback(callback: types.CallbackQuery):
    session_id = callback.data.replace("close_", "")
    close_edit_session(session_id)
    await callback.message.edit_text("✅ Сессия правок закрыта", reply_markup=main_menu())
    await safe_answer(callback)

@router.callback_query(F.data == "mode_text")
async def set_text_mode(callback: types.CallbackQuery):
    user_modes[callback.from_user.id] = "text"
    await callback.message.edit_text("🧠 Режим **Текст**\nПросто напиши мне вопрос!", reply_markup=main_menu())
    await safe_answer(callback)

@router.callback_query(F.data == "mode_image")
async def set_image_mode(callback: types.CallbackQuery):
    user_modes[callback.from_user.id] = "image"
    await callback.message.edit_text("🖼️ Режим **Картинка**\nНапиши запрос!", reply_markup=main_menu())
    await safe_answer(callback)

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
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])

    text = "🎨 **Выбери модель для генерации картинок:**\n\n"
    for key, model in IMAGE_MODELS.items():
        text += f"{model['name']} — {model['price']} токенов\n"
        text += f"   {model['description']}\n\n"

    await callback.message.edit_text(text, reply_markup=kb)
    await safe_answer(callback)

@router.callback_query(F.data.startswith("model_"))
async def set_model_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    model_key = callback.data.replace("model_", "")

    if model_key not in IMAGE_MODELS:
        await safe_answer(callback, "❌ Модель не найдена", show_alert=True)
        return

    user_model[user_id] = model_key
    model = IMAGE_MODELS[model_key]
    update_user_memory(user_id, {'preferred_model': model_key})

    await safe_answer(callback, f"✅ Выбрана модель: {model['name']}", show_alert=True)
    await callback.message.edit_text(
        f"✅ **Выбрана модель:** {model['name']}\n"
        f"💰 Стоимость: {model['price']} токенов\n"
        f"📝 {model['description']}\n\n"
        "Напиши описание и получи результат!",
        reply_markup=main_menu()
    )

@router.callback_query(F.data == "balance")
async def balance_cb(callback: types.CallbackQuery):
    await balance_cmd(callback.message)
    await safe_answer(callback)

@router.callback_query(F.data == "profile")
async def profile_cb(callback: types.CallbackQuery):
    await profile_cmd(callback.message)
    await safe_answer(callback)

@router.callback_query(F.data == "referral")
async def referral_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = force_create_user(user_id, callback.from_user.username or "")
    if not user:
        await safe_answer(callback, "❌ Ошибка!", show_alert=True)
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
    await safe_answer(callback)

@router.callback_query(F.data == "promo_use")
async def promo_use_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    user_pages[user_id] = {"state": "waiting_promo_use"}
    await callback.message.edit_text(
        "🎁 **Введите промокод**\n\nНапиши код, чтобы получить бонусные токены:\n\n⏹ /cancel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
    )
    await safe_answer(callback)

@router.callback_query(F.data == "buy_tokens")
async def buy_tokens_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 50 токенов (5 карт) — 10⭐", callback_data="token_50")],
        [InlineKeyboardButton(text="📦 200 токенов (20 карт) — 30⭐", callback_data="token_200")],
        [InlineKeyboardButton(text="📦 500 токенов (50 карт) — 60⭐", callback_data="token_500")],
        [InlineKeyboardButton(text="📦 1000 токенов (100 карт) — 120⭐", callback_data="token_1000")],
        [InlineKeyboardButton(text="📦 2500 токенов (250 карт) — 250⭐", callback_data="token_2500")],
        [InlineKeyboardButton(text="👑 Подписка", callback_data="subscription")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(
        "✨ **Купить токены**\n\n"
        "📦 **Пакеты токенов:**\n"
        "• 50 токенов (5 карт) — 10⭐\n"
        "• 200 токенов (20 карт) — 30⭐\n"
        "• 500 токенов (50 карт) — 60⭐\n"
        "• 1000 токенов (100 карт) — 120⭐\n"
        "• 2500 токенов (250 карт) — 250⭐\n\n"
        "👑 **Подписки:**\n"
        "• 💎 Премиум — 150⭐/мес (50 карт/день)\n"
        "• 👑 Премиум+ — 300⭐/мес (200 карт/день)\n\n"
        "Выберите пакет:",
        reply_markup=kb
    )
    await safe_answer(callback)

@router.callback_query(F.data == "subscription")
async def subscription_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Премиум — 150⭐/мес", callback_data="sub_premium")],
        [InlineKeyboardButton(text="👑 Премиум+ — 300⭐/мес", callback_data="sub_premium_plus")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="buy_tokens")]
    ])
    
    await callback.message.edit_text(
        "👑 **Подписки**\n\n"
        "💎 **Премиум** — 150⭐/мес\n"
        "• 50 картинок в день\n"
        "• Безлимит текстовых запросов\n"
        "• Без рекламы\n\n"
        "👑 **Премиум+** — 300⭐/мес\n"
        "• 200 картинок в день\n"
        "• Безлимит текстовых запросов\n"
        "• Приоритетная генерация\n"
        "• Персональная поддержка\n\n"
        "Выберите тариф:",
        reply_markup=kb
    )
    await safe_answer(callback)

@router.callback_query(F.data.startswith("sub_"))
async def subscribe_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    plan = callback.data.replace("sub_", "")
    
    if plan == "premium":
        stars = 150
        plan_name = "💎 Премиум"
        days = 30
    elif plan == "premium_plus":
        stars = 300
        plan_name = "👑 Премиум+"
        days = 30
    else:
        await safe_answer(callback, "❌ Неверный тариф", show_alert=True)
        return
    
    payload = secrets.token_hex(16)
    create_payment(user_id, stars, payload, f"subscription_{plan}")
    
    await callback.bot.send_invoice(
        chat_id=user_id,
        title=plan_name,
        description=f"Подписка на {days} дней",
        payload=payload,
        provider_token=PROVIDER_TOKEN,
        currency="XTR",
        prices=[LabeledPrice(label=plan_name, amount=stars)],
        start_parameter="subscribe"
    )
    await safe_answer(callback)

@router.callback_query(F.data.startswith("token_"))
async def token_pay_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")

    packs = {
        '50': (10, 50),
        '200': (30, 200),
        '500': (60, 500),
        '1000': (120, 1000),
        '2500': (250, 2500)
    }
    
    pack_type = callback.data.replace("token_", "")
    if pack_type not in packs:
        await safe_answer(callback, "❌ Неверный пакет", show_alert=True)
        return

    stars, tokens = packs[pack_type]
    payload = secrets.token_hex(16)
    create_payment(user_id, stars, payload, "tokens")

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
    await safe_answer(callback)

@router.message(F.successful_payment)
async def payment_success(message: types.Message):
    payload = message.successful_payment.invoice_payload
    payment = complete_payment(payload)

    if payment:
        stars, plan = payment['stars_amount'], payment['plan']
        
        # Обработка подписок
        if plan.startswith("subscription_"):
            plan_type = plan.replace("subscription_", "")
            if plan_type == "premium":
                days = 30
                plan_name = "💎 Премиум"
            elif plan_type == "premium_plus":
                days = 30
                plan_name = "👑 Премиум+"
            else:
                await message.answer("❌ Ошибка активации")
                return
            
            add_premium(message.from_user.id, days, plan_type, True)
            await message.answer(
                f"✅ Подписка активирована!\n"
                f"📦 План: {plan_name}\n"
                f"⏳ Длительность: {days} дней",
                reply_markup=main_menu()
            )
            return
        
        # Обработка токенов
        if plan == "tokens":
            packs = {10: 50, 30: 200, 60: 500, 120: 1000, 250: 2500}
            tokens = packs.get(stars, 0)
            if tokens > 0:
                add_tokens(message.from_user.id, tokens)
                await message.answer(f"✅ Оплачено! +{tokens} токенов!", reply_markup=main_menu())
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
    await safe_answer(callback)

@router.callback_query(F.data == "back_to_main")
async def back_main_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    tokens = get_tokens(user_id)
    used, max_req = get_text_requests(user_id)
    name = get_user_name(user_id) or "друг"

    text = (
        f"✨ **Vertex AI**\n\n"
        f"👋 Привет, {name}!\n"
        f"💰 Токенов: {tokens}\n"
        f"🖼️ 10 токенов = 1 картинка\n"
        f"✏️ 5 токенов = 1 правка\n"
        f"📝 Текст: {used}/{max_req} запросов сегодня\n\n"
        f"Напиши вопрос или выбери режим!"
    )
    await callback.message.edit_text(text, reply_markup=main_menu())
    await safe_answer(callback)

@router.callback_query(F.data == "help")
async def help_cb(callback: types.CallbackQuery):
    await help_cmd(callback.message)
    await safe_answer(callback)

@router.callback_query(F.data == "admin_panel")
async def admin_panel_cb(callback: types.CallbackQuery):
    if is_admin(callback.from_user.id):
        await callback.message.edit_text("🛡️ **АДМИН-ПАНЕЛЬ**", reply_markup=admin_kb())
        await safe_answer(callback)
    else:
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)


# ============================================================================
# ============================ АДМИН-ФУНКЦИИ ===============================
# ============================================================================

@router.callback_query(F.data == "a_stats")
async def a_stats_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    total, total_tokens, total_requests, total_images, premium_users = get_stats()

    text = (
        f"📊 **СТАТИСТИКА**\n\n"
        f"👥 Всего: {total}\n"
        f"💎 Премиум: {premium_users}\n"
        f"💰 Всего токенов: {total_tokens}\n"
        f"📝 Запросов: {total_requests}\n"
        f"🖼️ Картинок: {total_images}\n"
    )
    await callback.message.edit_text(text, reply_markup=admin_kb())
    await safe_answer(callback)

@router.callback_query(F.data == "a_model_stats")
async def a_model_stats_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    total = sum(model_stats.values())
    text = "📈 **СТАТИСТИКА МОДЕЛЕЙ**\n\n"
    text += f"Всего генераций: {total}\n\n"

    for key, count in model_stats.items():
        if count > 0:
            model = IMAGE_MODELS[key]
            percent = round(count / total * 100, 1) if total > 0 else 0
            text += f"{model['name']}\n   🔹 {count} ({percent}%)\n\n"

    if total == 0:
        text += "❌ Пока нет статистики."

    await callback.message.edit_text(text, reply_markup=admin_kb())
    await safe_answer(callback)

@router.callback_query(F.data == "a_users")
async def a_users_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, tokens, is_blocked FROM users WHERE user_id != 8676871187 ORDER BY tokens DESC LIMIT 20")
        users = cursor.fetchall()

    if not users:
        text = "👥 Нет пользователей"
    else:
        text = "👥 **Топ пользователей**\n\n"
        for u in users:
            status = "⛔" if u['is_blocked'] == 1 else "✅"
            name = u['username'] if u['username'] and u['username'] != str(u['user_id']) else "Без имени"
            text += f"{status} **{name}** (ID: {u['user_id']})\n   🪙 {u['tokens']} токенов\n\n"

    await callback.message.edit_text(text[:4000], reply_markup=admin_kb())
    await safe_answer(callback)

@router.callback_query(F.data == "a_give_tokens")
async def a_give_tokens_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    user_pages[callback.from_user.id] = {"state": "waiting_give_tokens"}
    await callback.message.edit_text(
        "⭐ **Раздать токены**\n\nФормат: `ID | количество`\nПример: `123456789 | 50`\n\nИли: `всем | 10`\n\n⏹ /cancel",
        reply_markup=admin_kb()
    )
    await safe_answer(callback)

@router.callback_query(F.data == "a_broadcast")
async def a_broadcast_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    user_pages[callback.from_user.id] = {"state": "waiting_broadcast"}
    await callback.message.edit_text("📢 **Рассылка**\n\nВведите текст.\n\n⏹ /cancel", reply_markup=admin_kb())
    await safe_answer(callback)

@router.callback_query(F.data == "a_block")
async def a_block_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, is_blocked FROM users WHERE user_id != 8676871187 ORDER BY user_id LIMIT 20")
        users = cursor.fetchall()

    if not users:
        await safe_answer(callback, "❌ Нет пользователей", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for u in users:
        name = u['username'] if u['username'] and u['username'] != str(u['user_id']) else str(u['user_id'])
        status = "✅" if u['is_blocked'] == 0 else "⛔"
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=f"{status} {name}", callback_data=f"block_user_{u['user_id']}")
        ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])

    await callback.message.edit_text("🚫 **Блокировка**\n\nНажмите на пользователя:", reply_markup=kb)
    await safe_answer(callback)

@router.callback_query(F.data.startswith("block_user_"))
async def block_user_action(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    user_id = int(callback.data.replace("block_user_", ""))
    user = get_user(user_id)
    if not user:
        await safe_answer(callback, "❌ Пользователь не найден", show_alert=True)
        return

    if user['is_blocked'] == 1:
        unblock_user(user_id)
        await safe_answer(callback, "✅ Разблокирован", show_alert=True)
    else:
        block_user(user_id)
        await safe_answer(callback, "⛔ Заблокирован", show_alert=True)

    do_backup()
    await a_block_cb(callback)

@router.callback_query(F.data == "a_messages")
async def a_messages_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_id, username, text, date, status FROM messages_to_admin ORDER BY date DESC LIMIT 20")
        messages = cursor.fetchall()

    if not messages:
        await callback.message.edit_text("📭 Нет обращений.", reply_markup=admin_kb())
        await safe_answer(callback)
        return

    text = "📩 **Обращения**\n\n"
    for msg in messages:
        status = "🆕" if msg['status'] == "new" else "✅"
        name = msg['username'] if msg['username'] and msg['username'] != str(msg['user_id']) else str(msg['user_id'])
        text += f"{status} {msg['user_id']} — {name}\n"
        text += f"📝 {msg['text'][:50]}{'...' if len(msg['text']) > 50 else ''}\n"
        text += f"🕐 {msg['date'][:16]}\n\n"

    await callback.message.edit_text(text[:4000], reply_markup=admin_kb())
    await safe_answer(callback)

@router.callback_query(F.data == "a_backup")
async def a_backup_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("⏳ Бэкап...")
    result = GitHubBackup().backup_db()
    await callback.message.edit_text("✅ Бэкап создан!" if result else "❌ Ошибка", reply_markup=admin_kb())
    await safe_answer(callback)

@router.callback_query(F.data == "a_export_db")
async def export_db_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    db_path = "data/repsolver.db"
    if not os.path.exists(db_path):
        await callback.message.edit_text("❌ Файл базы данных не найден!", reply_markup=admin_kb())
        await safe_answer(callback)
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
    await safe_answer(callback)

@router.callback_query(F.data == "a_restore_github")
async def restore_github_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    files = get_backup_list()
    if not files:
        await callback.message.edit_text(
            "❌ Нет бэкапов на GitHub!\n\nСначала создайте бэкап.",
            reply_markup=admin_kb()
        )
        await safe_answer(callback)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for f in files[:20]:
        name = f['name']
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=f"📄 {name[:30]}", callback_data=f"restore_backup_{name}")
        ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])

    await callback.message.edit_text(
        "📥 **Восстановление из GitHub**\n\nВыберите бэкап:",
        reply_markup=kb
    )
    await safe_answer(callback)

@router.callback_query(F.data.startswith("restore_backup_"))
async def restore_backup_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    filename = callback.data.replace("restore_backup_", "")
    await callback.message.edit_text(f"⏳ Восстанавливаю: `{filename}`...")

    success = restore_backup_from_github(filename)
    if success:
        await callback.message.edit_text("✅ **Бэкап восстановлен!**", reply_markup=admin_kb())
    else:
        await callback.message.edit_text("❌ **Ошибка восстановления!**", reply_markup=admin_kb())
    await safe_answer(callback)

@router.callback_query(F.data == "a_edit_prices")
async def a_edit_prices_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for key, model in IMAGE_MODELS.items():
        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{model['name']} — {model['price']} токенов",
                callback_data=f"edit_price_{key}"
            )
        ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])

    await callback.message.edit_text("💰 **Управление ценами**\n\nВыбери модель:", reply_markup=kb)
    await safe_answer(callback)


# ============================================================================
# ============================ 🎫 ПРОМОКОДЫ (АДМИНКА) =======================
# ============================================================================

@router.callback_query(F.data == "a_promocodes")
async def a_promocodes_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать промокод", callback_data="a_create_promo")],
        [InlineKeyboardButton(text="📋 Список промокодов", callback_data="a_list_promos")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])

    await callback.message.edit_text(
        "🎫 **Управление промокодами**\n\n"
        "Выберите действие:",
        reply_markup=kb
    )
    await safe_answer(callback)

@router.callback_query(F.data == "a_create_promo")
async def a_create_promo_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    user_pages[callback.from_user.id] = {"state": "waiting_promo_code"}
    await callback.message.edit_text(
        "🎫 **Создание промокода**\n\n"
        "Введите данные в формате:\n"
        "`код | бонус_токены | срок_дней`\n\n"
        "Пример: `WELCOME100 | 100 | 30`\n"
        "Бонус: 100 токенов, срок: 30 дней\n\n"
        "⏹ /cancel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="a_promocodes")]
        ])
    )
    await safe_answer(callback)

@router.callback_query(F.data == "a_list_promos")
async def a_list_promos_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM promocodes ORDER BY created_at DESC")
        promos = cursor.fetchall()

    if not promos:
        await callback.message.edit_text(
            "📋 **Список промокодов**\n\n"
            "❌ Нет созданных промокодов.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="a_promocodes")]
            ])
        )
        await safe_answer(callback)
        return

    text = "📋 **Список промокодов**\n\n"
    for p in promos:
        text += f"🔹 `{p['code']}`\n"
        text += f"   🪙 +{p['bonus_tokens']} токенов\n"
        text += f"   📊 Использован: {p['used']}/{p['max_uses']}\n"
        text += f"   ⏳ До: {p['expires_at'][:10]}\n\n"

    await callback.message.edit_text(
        text[:4000],
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="a_promocodes")]
        ])
    )
    await safe_answer(callback)


# ============================================================================
# ============================ ⭐ БАЛАНС STARS ============================
# ============================================================================

@router.callback_query(F.data == "a_stars_balance")
async def a_stars_balance_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return

    try:
        balance = await callback.bot.get_my_star_balance()
        
        # Примерный курс: 1 Star ≈ 0.013 BYN (может меняться)
        byn_approx = balance * 0.013
        rub_approx = balance * 0.45
        
        await callback.message.edit_text(
            f"⭐ **Баланс Telegram Stars**\n\n"
            f"На счету бота: **{balance}** Stars\n\n"
            f"💵 Примерно:\n"
            f"   • {byn_approx:.2f} BYN\n"
            f"   • {rub_approx:.2f} ₽\n\n"
            f"💡 Минимум для вывода: 1000 Stars\n"
            f"⏳ Вывод доступен через 21 день после получения\n"
            f"📊 1 Star ≈ 0.013 BYN (курс может меняться)",
            reply_markup=admin_kb()
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=admin_kb())
    await safe_answer(callback)


# ============================================================================
# ============================ АДМИН-ВВОД ==================================
# ============================================================================

async def handle_admin_input(message: types.Message):
    user_id = message.from_user.id
    state = user_pages.get(user_id, {})

    if message.text == "/cancel":
        user_pages.pop(user_id, None)
        await message.answer("✅ Отменено", reply_markup=admin_kb())
        return

    # === ПРОМОКОДЫ ===
    if state.get("state") == "waiting_promo_code":
        try:
            parts = message.text.strip().split("|")
            if len(parts) < 2:
                await message.answer("❌ Формат: код | токены | срок_дней")
                return

            code = parts[0].strip().upper()
            bonus = int(parts[1].strip())
            days = int(parts[2].strip()) if len(parts) > 2 else 30

            with get_db() as conn:
                cursor = conn.cursor()
                expires = (datetime.now() + timedelta(days=days)).isoformat()
                cursor.execute("""
                    INSERT INTO promocodes (code, bonus_tokens, max_uses, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (code, bonus, 100, datetime.now().isoformat(), expires))

            await message.answer(
                f"✅ Промокод создан!\n\n"
                f"📝 Код: `{code}`\n"
                f"🪙 Бонус: {bonus} токенов\n"
                f"⏳ Срок: {days} дней",
                reply_markup=admin_kb()
            )
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}", reply_markup=admin_kb())
        user_pages.pop(user_id, None)
        return

    # === ЦЕНЫ ===
    if state.get("state") == "waiting_price":
        try:
            new_price = int(message.text.strip())
            if new_price < 1:
                await message.answer("❌ Цена должна быть > 0!", reply_markup=admin_kb())
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

    # === РАЗДАЧА ТОКЕНОВ ===
    if state.get("state") == "waiting_give_tokens":
        try:
            text = message.text.strip()
            if text.startswith("всем") or text.startswith("all"):
                parts = text.split("|")
                if len(parts) < 2:
                    await message.answer("❌ Формат: всем | количество")
                    return
                amount = int(parts[1].strip())
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT user_id FROM users WHERE is_blocked = 0")
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
                add_tokens(target_id, amount)
                await message.answer(f"✅ Пользователю {target_id} начислено {amount} токенов!", reply_markup=admin_kb())
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}", reply_markup=admin_kb())
        user_pages.pop(user_id, None)
        return

    # === РАССЫЛКА ===
    if state.get("state") == "waiting_broadcast":
        if not message.text or not message.text.strip():
            await message.answer("❌ Текст не может быть пустым!", reply_markup=admin_kb())
            user_pages.pop(user_id, None)
            return

        await message.answer("📢 Рассылка...")
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

    # === ОБРАЩЕНИЕ В ПОДДЕРЖКУ ===
    if state.get("state") == "waiting_contact":
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO messages_to_admin (user_id, username, text, date) VALUES (?, ?, ?, ?)",
                          (user_id, message.from_user.username or "", message.text, datetime.now().isoformat()))
        await message.bot.send_message(ADMIN_ID, f"📩 От {user_id}:\n{message.text}")
        await message.answer("✅ Отправлено!", reply_markup=main_menu())
        user_pages.pop(user_id, None)
        return


# ============================================================================
# ============================ ФУНКЦИИ ДЛЯ GITHUB ==========================
# ============================================================================

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


# ============================================================================
# ============================ ГЛОБАЛЬНЫЙ ОБРАБОТЧИК ОШИБОК =================
# ============================================================================

@router.errors()
async def global_error_handler(event: types.ErrorEvent):
    """Ловит ВСЕ ошибки — пользователь ничего не видит"""
    error = event.exception
    logger.error(f"❌ Ошибка (обработана): {error}")
    
    try:
        if hasattr(event, 'update') and event.update:
            update = event.update
            
            if hasattr(update, 'callback_query') and update.callback_query:
                callback = update.callback_query
                try:
                    await safe_answer(callback)
                except:
                    pass
                try:
                    await callback.message.answer(
                        "⚠️ Произошла ошибка. Попробуйте ещё раз или напишите /start",
                        reply_markup=main_menu()
                    )
                except:
                    pass
            
            elif hasattr(update, 'message') and update.message:
                try:
                    await update.message.answer(
                        "⚠️ Что-то пошло не так. Попробуйте ещё раз или напишите /start",
                        reply_markup=main_menu()
                    )
                except:
                    pass
    except:
        pass
    
    return True
