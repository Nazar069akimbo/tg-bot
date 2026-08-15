from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, BufferedInputFile
from aiogram.exceptions import TelegramBadRequest
from database.db import *
from ai.client import solve_problem
from backup import GitHubBackup
import logging, secrets, os, requests, asyncio, json, re, time
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from openai import OpenAI

router = Router()
logger = logging.getLogger(__name__)

# ===== СОСТОЯНИЯ =====
user_pages = {}
user_model = {}

# ===== КОНСТАНТЫ =====
ADMIN_CODE = "30121979"
API_KEY = os.getenv('OPENAI_API_KEY')
PROVIDER_TOKEN = os.getenv('PROVIDER_TOKEN', '')
PROMPT_MODEL = "gpt-4.1-nano"
ADMIN_ID = int(os.getenv('ADMIN_ID', 6957852385))

# ===== МОДЕЛИ =====
IMAGE_MODELS = {
    "flux": {"name": "🖼️ Flux Schnell", "price": 10, "api_model": "flux-schnell", "type": "replicate", "description": "⚡ Быстрая, базовая"},
    "flux_2_max": {"name": "🔥 Flux-2-Max", "price": 100, "api_model": "flux-2-max", "type": "replicate", "description": "⭐ ТОПОВОЕ КАЧЕСТВО"}
}
model_stats = {"flux": 0, "flux_2_max": 0}

# ===== КЛИЕНТ =====
client = OpenAI(api_key=API_KEY, base_url='https://openai.bothub.chat/v1') if API_KEY else None


# ============================================================================
# =========================== ЛОГГЕР ========================================
# ============================================================================

def log_info(user_id, action, details=""):
    """Логирование действий"""
    logger.info(f"📌 [{user_id}] {action}: {details}")

def log_error(user_id, action, error):
    """Логирование ошибок"""
    logger.error(f"❌ [{user_id}] {action}: {error}")

def log_success(user_id, action, details=""):
    """Логирование успеха"""
    logger.info(f"✅ [{user_id}] {action}: {details}")


# ============================================================================
# =========================== БЕЗОПАСНЫЕ ФУНКЦИИ ===========================
# ============================================================================

async def safe_answer(callback: types.CallbackQuery, text: str = None, show_alert: bool = False):
    try:
        if text:
            await callback.answer(text, show_alert=show_alert)
        else:
            await callback.answer()
        log_info(callback.from_user.id, "callback_answer", text or "ok")
    except TelegramBadRequest as e:
        log_error(callback.from_user.id, "callback_answer", str(e))
    except Exception as e:
        log_error(callback.from_user.id, "callback_answer", str(e))

def get_user_name(user_id):
    memory = get_user_memory(user_id)
    if memory and memory.get('name'):
        return memory['name']
    return None


# ============================================================================
# =========================== УМНЫЙ АНАЛИЗ ЧЕРЕЗ ИИ =========================
# ============================================================================

async def ai_detect_intent(user_id, text):
    """Использует нейросеть, чтобы понять, что хочет пользователь"""
    log_info(user_id, "ai_analyze", f"Запрос: {text[:50]}...")
    
    if not API_KEY:
        log_error(user_id, "ai_analyze", "API_KEY отсутствует")
        return 'chat', {}

    system_prompt = """Ты — ИИ-ассистент бота Vertex AI. Определи, что хочет пользователь.

Верни ТОЛЬКО JSON (без пояснений):
{"action": "действие", "params": {}}

Действия:
- generate_image: пользователь хочет создать картинку
- edit_image: пользователь хочет изменить существующую картинку
- show_prices: пользователь спрашивает о ценах
- show_balance: пользователь спрашивает баланс
- show_referral: пользователь спрашивает о рефералах
- chat: обычный разговор"""

    try:
        start_time = time.time()
        resp = requests.post(
            "https://openai.bothub.chat/v1/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "model": PROMPT_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Запрос: {text}"}
                ],
                "max_tokens": 100,
                "temperature": 0.1
            },
            timeout=10
        )
        elapsed = time.time() - start_time
        log_info(user_id, "ai_analyze", f"Ответ за {elapsed:.2f}с, статус: {resp.status_code}")
        
        if resp.status_code == 200:
            result = resp.json().get('choices', [{}])[0].get('message', {}).get('content', '{}')
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                action = data.get('action', 'chat')
                log_info(user_id, "ai_analyze", f"Результат: {action}")
                return action, data.get('params', {})
    except Exception as e:
        log_error(user_id, "ai_analyze", str(e))
    
    return 'chat', {}


# ============================================================================
# ================================ КЛАВИАТУРЫ ================================
# ============================================================================

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✨ Купить токены", callback_data="buy_tokens"),
         InlineKeyboardButton(text="📊 Баланс", callback_data="balance")],
        [InlineKeyboardButton(text="🎁 Промокод", callback_data="promo_use"),
         InlineKeyboardButton(text="👥 Рефералы", callback_data="referral")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="❓ Помощь", callback_data="help")],
        [InlineKeyboardButton(text="🛡️ Админ", callback_data="admin_panel")]
    ])

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="a_stats"), InlineKeyboardButton(text="📈 Модели", callback_data="a_model_stats")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="a_users"), InlineKeyboardButton(text="⭐ Раздать токены", callback_data="a_give_tokens")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="a_broadcast"), InlineKeyboardButton(text="🚫 Блокировка", callback_data="a_block")],
        [InlineKeyboardButton(text="💾 Бэкап", callback_data="a_backup"), InlineKeyboardButton(text="📩 Обращения", callback_data="a_messages")],
        [InlineKeyboardButton(text="📤 Выгрузить БД", callback_data="a_export_db"), InlineKeyboardButton(text="📥 Восстановить из GitHub", callback_data="a_restore_github")],
        [InlineKeyboardButton(text="💰 Цены", callback_data="a_edit_prices"), InlineKeyboardButton(text="🎫 Промокоды", callback_data="a_promocodes")],
        [InlineKeyboardButton(text="⭐ Баланс Stars", callback_data="a_stars_balance")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

def image_action_buttons(image_id, session_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Поправить", callback_data=f"edit_{image_id}")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]
    ])

def edit_in_progress_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏹ Отмена", callback_data="cancel_edit")]
    ])


# ============================================================================
# ============================== КОМАНДЫ ====================================
# ============================================================================

@router.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    log_info(user_id, "start", "Команда /start")
    
    username = message.from_user.username or ""
    user = force_create_user(user_id, username)
    if not user:
        log_error(user_id, "start", "Ошибка регистрации")
        await message.answer("❌ Ошибка регистрации.")
        return

    memory = get_user_memory(user_id)
    if not memory or not memory.get('name'):
        user_pages[user_id] = {"state": "waiting_name"}
        await message.answer(
            "👋 Привет! Я — **Vertex AI** — твой умный ассистент.\n\n"
            "✨ Я понимаю естественный язык и сам решаю, что делать:\n"
            "• 🖼️ Генерировать картинки\n"
            "• ✏️ Редактировать картинки\n"
            "• 💰 Показывать цены\n"
            "• 🧠 Отвечать на вопросы\n\n"
            "Просто напиши, что хочешь!\n\n"
            "Как мне тебя называть?"
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

    text = (
        f"✨ **Vertex AI**\n\n"
        f"👋 С возвращением, {name}!\n"
        f"💰 Токенов: {tokens}\n"
        f"🖼️ 10 токенов = 1 картинка\n"
        f"📝 Текст: {used}/{max_req} запросов сегодня\n\n"
        f"{trial_text}\n\n"
        f"💬 Просто напиши, что хочешь сделать!"
    )
    await message.answer(text, reply_markup=main_menu())
    log_success(user_id, "start", "Бот запущен")

@router.message(Command("balance"))
async def balance_cmd(message: types.Message):
    user_id = message.from_user.id
    tokens = get_tokens(user_id)
    used, max_req = get_text_requests(user_id)
    await message.answer(
        f"💰 **Баланс**\n\n"
        f"🪙 Токенов: {tokens}\n"
        f"🖼️ Хватит на: {tokens // 10} картинок\n"
        f"📝 Текст: {used}/{max_req} запросов сегодня",
        reply_markup=main_menu()
    )
    log_info(user_id, "balance", f"Токенов: {tokens}")

@router.message(Command("profile"))
async def profile_cmd(message: types.Message):
    user_id = message.from_user.id
    tokens = get_tokens(user_id)
    name = get_user_name(user_id) or "Не указано"
    await message.answer(
        f"👤 **Мой профиль**\n\n"
        f"🆔 ID: {user_id}\n"
        f"👤 Имя: {name}\n"
        f"💰 Токенов: {tokens}\n"
        f"🖼️ Картинок: {tokens // 10}",
        reply_markup=main_menu()
    )
    log_info(user_id, "profile", f"Имя: {name}, токенов: {tokens}")

@router.message(Command("help"))
async def help_cmd(message: types.Message):
    text = (
        "❓ **Помощь**\n\n"
        "🖼️ **Картинка** — скажи *нарисуй кота*\n"
        "✏️ **Правка** — скажи *сделай кота чёрным*\n"
        "💰 **Цены** — спроси *сколько стоит премиум*\n"
        "📊 **Баланс** — спроси *мой баланс*\n"
        "👥 **Рефералы** — спроси *как пригласить друга*\n\n"
        "📌 Команды: /start, /balance, /profile, /help"
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


# ============================================================================
# ============================ ОСНОВНОЙ ОБРАБОТЧИК =========================
# ============================================================================

@router.message(F.text)
async def handle_message(message: types.Message):
    if not message.text or message.text.startswith("/"):
        return

    user_id = message.from_user.id
    text = message.text.strip()
    log_info(user_id, "handle_message", f"Текст: {text[:50]}...")

    state = user_pages.get(user_id, {})

    # === ОБРАБОТКА СОСТОЯНИЙ ===
    if state.get("state") == "waiting_name":
        set_user_name(user_id, text)
        user_pages.pop(user_id, None)
        await message.answer(f"✅ Отлично! Я запомнил тебя.")
        await start_cmd(message)
        return

    if state.get("state") == "waiting_promo_use":
        success, msg = use_promocode(text.upper(), user_id)
        await message.answer(msg, reply_markup=main_menu())
        user_pages.pop(user_id, None)
        log_info(user_id, "promo_use", f"Код: {text}, результат: {success}")
        return

    if state.get("state") in ["waiting_broadcast", "waiting_block_user", "waiting_contact",
                              "waiting_give_tokens", "waiting_price", "waiting_promo_code"]:
        await handle_admin_input(message)
        return

    if state.get("state") == "waiting_edit":
        await handle_edit(message)
        return

    # === УМНЫЙ АНАЛИЗ ===
    log_info(user_id, "handle_message", "Запуск AI анализа...")
    action, params = await ai_detect_intent(user_id, text)
    log_info(user_id, "handle_message", f"AI результат: {action}")

    if action == 'generate_image':
        await generate_image(message, params.get('prompt', text))
    elif action == 'edit_image':
        last_img = get_last_image(user_id)
        if last_img:
            await handle_edit_with_context(message, params.get('prompt', text))
        else:
            await message.answer("🤔 У тебя нет предыдущей картинки. Сначала сгенерируй!")
            await generate_image(message, text)
    elif action == 'show_prices':
        await send_price_info(message)
    elif action == 'show_balance':
        await balance_cmd(message)
    elif action == 'show_referral':
        await send_referral_info(message)
    else:
        await generate_text(message)


# ============================================================================
# =========================== ГЕНЕРАЦИЯ КАРТИНОК ===========================
# ============================================================================

async def generate_image(message: types.Message, prompt=None):
    user_id = message.from_user.id
    log_info(user_id, "generate_image", f"Начало, промпт: {prompt[:50] if prompt else 'None'}...")
    
    user = force_create_user(user_id, message.from_user.username or "")
    if not user:
        log_error(user_id, "generate_image", "Ошибка регистрации")
        await message.answer("❌ Ошибка!", reply_markup=main_menu())
        return

    if not prompt:
        prompt = message.text

    model_key = user_model.get(user_id, "flux")
    model_config = IMAGE_MODELS.get(model_key, IMAGE_MODELS["flux"])
    price = model_config["price"]
    log_info(user_id, "generate_image", f"Модель: {model_key}, цена: {price}")

    tokens = get_tokens(user_id)
    if tokens < price:
        trial = get_trial_remaining(user_id)
        if trial > 0:
            log_info(user_id, "generate_image", f"Недостаточно токенов, пробный период: {trial}")
            await message.answer(f"⚠️ Нужно {price} токенов. У тебя {tokens}. Пробный период: {trial} дней.")
            return
        log_info(user_id, "generate_image", f"Недостаточно токенов: {tokens} < {price}")
        await message.answer(f"❌ Недостаточно токенов! Нужно: {price}, у тебя: {tokens}\n✨ Купи токены!", reply_markup=main_menu())
        return

    if not API_KEY:
        log_error(user_id, "generate_image", "API_KEY отсутствует")
        return await message.answer("❌ API ключ не настроен")

    status_msg = await message.answer(f"🎨 Генерирую картинку...")
    log_info(user_id, "generate_image", "Начало генерации...")

    try:
        # Улучшаем промпт через GPT (дёшево, ~30 CAPS)
        log_info(user_id, "generate_image", "Улучшение промпта через GPT...")
        start_time = time.time()
        prompt_resp = requests.post(
            "https://openai.bothub.chat/v1/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "model": PROMPT_MODEL,
                "messages": [
                    {"role": "system", "content": "Create detailed English prompt for image generation. Only the prompt!"},
                    {"role": "user", "content": f"Prompt for: {prompt}"}
                ],
                "max_tokens": 200
            },
            timeout=30
        )
        elapsed = time.time() - start_time
        log_info(user_id, "generate_image", f"GPT ответ за {elapsed:.2f}с, статус: {prompt_resp.status_code}")
        
        enhanced = prompt
        if prompt_resp.status_code == 200:
            enhanced = prompt_resp.json().get('choices', [{}])[0].get('message', {}).get('content', prompt).strip('"')
            log_info(user_id, "generate_image", f"Улучшенный промпт: {enhanced[:50]}...")

        # Генерация картинки через Replicate
        log_info(user_id, "generate_image", "Запрос к Replicate...")
        start_time = time.time()
        img_resp = requests.post(
            "https://bothub.chat/api/v2/replicate/v1/images/generations",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "model": model_config["api_model"],
                "input": {"prompt": enhanced, "aspect_ratio": "1:1", "output_format": "webp"},
                "bothub": {"include_usage": True, "return_base64": False}
            },
            timeout=120
        )
        elapsed = time.time() - start_time
        log_info(user_id, "generate_image", f"Replicate ответ за {elapsed:.2f}с, статус: {img_resp.status_code}")

        img_data = None
        try:
            # Используем OpenAI клиент для генерации
            log_info(user_id, "generate_image", "Запрос к OpenAI клиенту...")
            params = {
                'model': model_config["api_model"],
                'prompt': enhanced,
                'n': 1,
                'size': '1024x1024',
            }
            req = client.images.generate(**params)
            log_info(user_id, "generate_image", f"OpenAI ответ получен")
            
            # Получаем URL картинки
            image_url = json.loads(req.model_dump_json())['data'][0]['url']
            log_info(user_id, "generate_image", f"Скачивание картинки...")
            
            if image_url:
                img_data_response = requests.get(image_url, timeout=30)
                if img_data_response.status_code == 200 and len(img_data_response.content) > 1000:
                    img_data = img_data_response.content
                    log_info(user_id, "generate_image", f"Картинка скачана, размер: {len(img_data)} байт")
        except Exception as e:
            log_error(user_id, "generate_image", f"OpenAI ошибка: {e}")
            # Пробуем через старый метод (Replicate)
            log_info(user_id, "generate_image", "Попытка через Replicate API...")
            img_resp = requests.post(
                "https://bothub.chat/api/v2/replicate/v1/images/generations",
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": model_config["api_model"],
                    "input": {"prompt": enhanced, "aspect_ratio": "1:1", "output_format": "webp"},
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
                        log_info(user_id, "generate_image", f"Replicate картинка скачана")

        if img_data:
            # Водяной знак
            try:
                img = Image.open(BytesIO(img_data))
                draw = ImageDraw.Draw(img)
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
                except:
                    font = ImageFont.load_default()
                draw.text((10, 10), "Vertex AI", font=font, fill=(255, 255, 255, 128))
                output = BytesIO()
                img.save(output, format='PNG')
                output.seek(0)
                img_data = output.getvalue()
            except Exception as e:
                log_error(user_id, "generate_image", f"Ошибка водяного знака: {e}")

            # Списываем токены
            spend_tokens(user_id, price)
            log_info(user_id, "generate_image", f"Списано {price} токенов")

            # Сохраняем в БД
            log_info(user_id, "generate_image", "Сохранение в БД...")
            try:
                image_id, session_id = save_image_to_history(
                    user_id=user_id, prompt=prompt, enhanced_prompt=enhanced,
                    model=model_key, image_data=img_data
                )
                log_info(user_id, "generate_image", f"Сохранено в БД, image_id: {image_id}")
            except Exception as e:
                log_error(user_id, "generate_image", f"Ошибка сохранения в БД: {e}")
                # Даже если не сохранилось, отправляем картинку
                image_id = None
                session_id = None

            # Отправляем пользователю
            new_tokens = get_tokens(user_id)
            log_info(user_id, "generate_image", f"Отправка картинки, осталось токенов: {new_tokens}")
            await message.answer_photo(
                BufferedInputFile(file=img_data, filename="image.png"),
                caption=f"🖼️ **Твоя картинка**\n📝 {prompt[:50]}\n💰 -{price} токенов | 🪙 {new_tokens} осталось",
                reply_markup=image_action_buttons(image_id, session_id) if image_id else None
            )
            await status_msg.delete()
            log_success(user_id, "generate_image", "Картинка отправлена")
            return

        log_error(user_id, "generate_image", "Не удалось получить картинку")
        await status_msg.edit_text("❌ Не удалось получить картинку")
    except Exception as e:
        log_error(user_id, "generate_image", str(e))
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")


# ============================================================================
# ============================ ТЕКСТОВЫЙ ИИ ==================================
# ============================================================================

async def generate_text(message: types.Message):
    user_id = message.from_user.id
    log_info(user_id, "generate_text", f"Начало, текст: {message.text[:50]}...")
    
    if not can_request_text(user_id):
        log_info(user_id, "generate_text", "Лимит исчерпан")
        await message.answer("🔒 Лимит текстовых запросов исчерпан! Завтра будет новый день.", reply_markup=main_menu())
        return

    status_msg = await message.answer("🤔 Думаю...")
    try:
        answer = solve_problem(message.text, "chat", False)
        add_text_request(user_id)
        do_backup()
        used, max_req = get_text_requests(user_id)
        add_to_context(user_id, message.text)
        await status_msg.edit_text(f"🧠 {answer}\n\n📝 Осталось: {max_req - used}/{max_req}")
        log_success(user_id, "generate_text", f"Ответ: {answer[:50]}...")
    except Exception as e:
        log_error(user_id, "generate_text", str(e))
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")


# ============================================================================
# ============================ ОСТАЛЬНЫЕ ФУНКЦИИ ===========================
# ============================================================================

async def send_price_info(message: types.Message):
    user_id = message.from_user.id
    log_info(user_id, "send_price_info", "Показ цен")
    text = (
        "💰 **Цены и тарифы**\n\n"
        "📦 **Пакеты токенов:**\n"
        "• 50 токенов (5 карт) — 10⭐\n"
        "• 200 токенов (20 карт) — 30⭐\n"
        "• 500 токенов (50 карт) — 60⭐\n"
        "• 1000 токенов (100 карт) — 120⭐\n"
        "• 2500 токенов (250 карт) — 250⭐\n\n"
        "👑 **Подписки:**\n"
        "• 💎 Премиум — 150⭐/мес (50 карт/день)\n"
        "• 👑 Премиум+ — 300⭐/мес (200 карт/день)\n\n"
        "💡 1 Star ≈ 0.45 ₽\n\n"
        "➡️ Нажми «Купить токены» в меню!"
    )
    await message.answer(text, reply_markup=main_menu())

async def send_referral_info(message: types.Message):
    user_id = message.from_user.id
    log_info(user_id, "send_referral_info", "Показ рефералов")
    count = get_referral_count(user_id)
    link = f"https://t.me/Vertex1bot?start={user_id}"
    text = (
        "👥 **Рефералы**\n\n"
        f"👤 Приглашено: {count}\n"
        f"🎁 Бонус: +20 токенов за друга\n\n"
        f"🔗 Твоя ссылка:\n{link}"
    )
    await message.answer(text, reply_markup=main_menu())

async def handle_edit_with_context(message: types.Message, edit_text: str):
    user_id = message.from_user.id
    log_info(user_id, "handle_edit", f"Правка: {edit_text}")
    last_img = get_last_image(user_id)
    if not last_img:
        log_info(user_id, "handle_edit", "Нет предыдущей картинки")
        await message.answer("❌ Нет предыдущей картинки для правки")
        return

    session_id = last_img.get('session_id')
    full_prompt = last_img.get('prompt', '')
    new_prompt = f"{full_prompt}, {edit_text}"
    await generate_image(message, new_prompt)

async def handle_edit(message: types.Message):
    user_id = message.from_user.id
    state = user_pages.get(user_id, {})
    image_id = state.get("image_id")
    if not image_id:
        await message.answer("❌ Нет картинки для правки")
        return

    last_img = get_image_by_id(image_id)
    if not last_img:
        await message.answer("❌ Картинка не найдена")
        return

    await handle_edit_with_context(message, message.text)
    user_pages.pop(user_id, None)


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

    if state.get("state") == "waiting_promo_code":
        try:
            parts = message.text.strip().split("|")
            if len(parts) < 2:
                await message.answer("❌ Формат: код | токены | дни")
                return
            code = parts[0].strip().upper()
            bonus = int(parts[1].strip())
            days = int(parts[2].strip()) if len(parts) > 2 else 30
            conn = get_db()
            cursor = conn.cursor()
            expires = (datetime.now() + timedelta(days=days)).isoformat()
            cursor.execute("INSERT INTO promocodes (code, bonus_tokens, max_uses, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                           (code, bonus, 100, datetime.now().isoformat(), expires))
            conn.commit()
            conn.close()
            log_info(user_id, "admin_promo", f"Создан промокод {code} на {bonus} токенов")
            await message.answer(f"✅ Промокод `{code}` создан! +{bonus} токенов, {days} дней", reply_markup=admin_kb())
        except Exception as e:
            log_error(user_id, "admin_promo", str(e))
            await message.answer(f"❌ Ошибка: {e}", reply_markup=admin_kb())
        user_pages.pop(user_id, None)
        return

    if state.get("state") == "waiting_price":
        try:
            new_price = int(message.text.strip())
            if new_price < 1:
                await message.answer("❌ Цена > 0", reply_markup=admin_kb())
                return
            model_key = state.get("model")
            if model_key and model_key in IMAGE_MODELS:
                IMAGE_MODELS[model_key]["price"] = new_price
                log_info(user_id, "admin_price", f"{model_key} цена: {new_price}")
                await message.answer(f"✅ Цена обновлена: {new_price}", reply_markup=admin_kb())
        except:
            await message.answer("❌ Введи число", reply_markup=admin_kb())
        user_pages.pop(user_id, None)
        return

    if state.get("state") == "waiting_give_tokens":
        try:
            text = message.text.strip()
            if text.startswith("всем") or text.startswith("all"):
                parts = text.split("|")
                amount = int(parts[1].strip()) if len(parts) > 1 else 10
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("SELECT user_id FROM users WHERE is_blocked = 0")
                users = cursor.fetchall()
                conn.close()
                count = 0
                for u in users:
                    add_tokens(u['user_id'], amount)
                    count += 1
                log_info(user_id, "admin_give_tokens", f"Всем по {amount}, {count} пользователей")
                await message.answer(f"✅ Раздано {amount} токенов {count} пользователям", reply_markup=admin_kb())
            else:
                parts = text.split("|")
                if len(parts) < 2:
                    await message.answer("❌ Формат: ID | количество")
                    return
                target_id = int(parts[0].strip())
                amount = int(parts[1].strip())
                add_tokens(target_id, amount)
                log_info(user_id, "admin_give_tokens", f"{target_id} +{amount} токенов")
                await message.answer(f"✅ {target_id} +{amount} токенов", reply_markup=admin_kb())
        except Exception as e:
            log_error(user_id, "admin_give_tokens", str(e))
            await message.answer("❌ Ошибка", reply_markup=admin_kb())
        user_pages.pop(user_id, None)
        return

    if state.get("state") == "waiting_broadcast":
        if not message.text or not message.text.strip():
            await message.answer("❌ Пустой текст", reply_markup=admin_kb())
            user_pages.pop(user_id, None)
            return
        await message.answer("📢 Рассылка...")
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE is_blocked = 0")
        users = cursor.fetchall()
        conn.close()
        sent = 0
        for u in users:
            try:
                await message.bot.send_message(u['user_id'], f"📢 {message.text}")
                sent += 1
                await asyncio.sleep(0.05)
            except:
                pass
        log_info(user_id, "admin_broadcast", f"Отправлено {sent} пользователям")
        await message.answer(f"✅ Отправлено: {sent}", reply_markup=admin_kb())
        do_backup()
        user_pages.pop(user_id, None)
        return

    if state.get("state") == "waiting_contact":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO messages_to_admin (user_id, username, text, date) VALUES (?, ?, ?, ?)",
                       (user_id, message.from_user.username or "", message.text, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        await message.bot.send_message(ADMIN_ID, f"📩 От {user_id}:\n{message.text}")
        await message.answer("✅ Отправлено!", reply_markup=main_menu())
        user_pages.pop(user_id, None)
        return


# ============================================================================
# ============================ ГЛОБАЛЬНЫЙ ОБРАБОТЧИК =======================
# ============================================================================

@router.errors()
async def global_error_handler(event: types.ErrorEvent):
    error = event.exception
    logger.error(f"❌ ГЛОБАЛЬНАЯ ОШИБКА: {error}")
    try:
        if hasattr(event, 'update') and event.update:
            update = event.update
            if hasattr(update, 'callback_query') and update.callback_query:
                try:
                    await safe_answer(update.callback_query)
                except:
                    pass
                try:
                    await update.callback_query.message.answer(
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
