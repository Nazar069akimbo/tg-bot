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
    logger.info(f"📌 [{user_id}] {action}: {details}")

def log_error(user_id, action, error):
    logger.error(f"❌ [{user_id}] {action}: {error}")

def log_success(user_id, action, details=""):
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
    except TelegramBadRequest:
        pass
    except Exception:
        pass

def get_user_name(user_id):
    memory = get_user_memory(user_id)
    if memory and memory.get('name'):
        return memory['name']
    return None


# ============================================================================
# =========================== ГИБРИДНЫЙ АНАЛИЗ ==============================
# ============================================================================

async def detect_intent_hybrid(user_id, text):
    """Гибридный анализ: сначала ключевые слова, потом нейросеть"""
    text_lower = text.lower()
    
    # === КЛЮЧЕВЫЕ СЛОВА (БЕСПЛАТНО) ===
    image_keywords = [
        'нарисуй', 'сгенерируй', 'покажи', 'картинку', 'изображение',
        'кота', 'пейзаж', 'портрет', 'создай', 'нарисуй мне',
        'красивый', 'рисунок', 'иллюстрация', 'фото', 'изобрази'
    ]
    
    if any(word in text_lower for word in image_keywords):
        log_info(user_id, "detect_intent", "🔑 Ключевые слова: image")
        return 'generate_image', {'prompt': text}
    
    price_keywords = ['цена', 'стоит', 'подписка', 'премиум', 'сколько', 'рублей', 'звёзд']
    if any(word in text_lower for word in price_keywords):
        log_info(user_id, "detect_intent", "🔑 Ключевые слова: prices")
        return 'show_prices', {}
    
    referral_keywords = ['реферал', 'пригласить', 'друг', 'ссылка']
    if any(word in text_lower for word in referral_keywords):
        log_info(user_id, "detect_intent", "🔑 Ключевые слова: referral")
        return 'show_referral', {}
    
    balance_keywords = ['баланс', 'токенов', 'сколько токенов']
    if any(word in text_lower for word in balance_keywords):
        log_info(user_id, "detect_intent", "🔑 Ключевые слова: balance")
        return 'show_balance', {}
    
    # === НЕЙРОСЕТЬ (ЕСЛИ НЕ ПОНЯТНО) ===
    log_info(user_id, "detect_intent", "🧠 Ключевые слова не сработали, запускаем AI...")
    return await ai_detect_intent(user_id, text)


async def ai_detect_intent(user_id, text):
    """Использует нейросеть, чтобы понять, что хочет пользователь"""
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

    # === ГИБРИДНЫЙ АНАЛИЗ ===
    log_info(user_id, "handle_message", "Запуск гибридного анализа...")
    action, params = await detect_intent_hybrid(user_id, text)
    log_info(user_id, "handle_message", f"Результат: {action}")

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
        # Улучшаем промпт через GPT
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

        # === ГЕНЕРАЦИЯ ЧЕРЕЗ OPENAI КЛИЕНТ ===
        img_data = None
        try:
            log_info(user_id, "generate_image", "Запрос к OpenAI клиенту...")
            params = {
                'model': model_config["api_model"],
                'prompt': enhanced,
                'n': 1,
                'size': '1024x1024',
            }
            req = client.images.generate(**params)
            log_info(user_id, "generate_image", "OpenAI ответ получен")
            # Получаем URL картинки (безопасно)
            if hasattr(req, 'data') and len(req.data) > 0:
                image_url = req.data[0].url
                log_info(user_id, "generate_image", f"URL получен: {image_url[:50]}...")
            else:
                log_error(user_id, "generate_image", "Нет data в ответе OpenAI")
                image_url = None
            
            if image_url:
                log_info(user_id, "generate_image", f"Скачивание картинки...")
                img_data_response = requests.get(image_url, timeout=30)
                if img_data_response.status_code == 200 and len(img_data_response.content) > 1000:
                    img_data = img_data_response.content
                    log_info(user_id, "generate_image", f"Картинка скачана, размер: {len(img_data)} байт")
                else:
                    log_error(user_id, "generate_image", f"Ошибка скачивания: {img_data_response.status_code}, размер: {len(img_data_response.content)}")
        except Exception as e:
            log_error(user_id, "generate_image", f"OpenAI ошибка: {e}")
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
                        log_info(user_id, "generate_image", "Replicate картинка скачана")

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
# ============================ ПРАВКИ КАРТИНОК =============================
# ============================================================================

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
# ============================ ИНФОРМАЦИЯ ==================================
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


# ============================================================================
# ============================ КНОПКИ (ПЛАТЕЖИ) ============================
# ============================================================================

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
    await send_referral_info(callback.message)
    await safe_answer(callback)

@router.callback_query(F.data == "promo_use")
async def promo_use_cb(callback: types.CallbackQuery):
    user_pages[callback.from_user.id] = {"state": "waiting_promo_use"}
    await callback.message.edit_text("🎁 **Введите промокод**\n\n⏹ /cancel", reply_markup=main_menu())
    await safe_answer(callback)

@router.callback_query(F.data == "buy_tokens")
async def buy_tokens_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 50 токенов — 10⭐", callback_data="token_50")],
        [InlineKeyboardButton(text="📦 200 токенов — 30⭐", callback_data="token_200")],
        [InlineKeyboardButton(text="📦 500 токенов — 60⭐", callback_data="token_500")],
        [InlineKeyboardButton(text="📦 1000 токенов — 120⭐", callback_data="token_1000")],
        [InlineKeyboardButton(text="📦 2500 токенов — 250⭐", callback_data="token_2500")],
        [InlineKeyboardButton(text="👑 Подписка", callback_data="subscription")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])
    await callback.message.edit_text("✨ **Купить токены**\n\nВыбери пакет:", reply_markup=kb)
    await safe_answer(callback)

@router.callback_query(F.data == "subscription")
async def subscription_cb(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Премиум — 150⭐/мес", callback_data="sub_premium")],
        [InlineKeyboardButton(text="👑 Премиум+ — 300⭐/мес", callback_data="sub_premium_plus")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="buy_tokens")]
    ])
    await callback.message.edit_text("👑 **Подписки**\n\n💎 Премиум — 150⭐/мес (50 карт/день)\n👑 Премиум+ — 300⭐/мес (200 карт/день)", reply_markup=kb)
    await safe_answer(callback)

@router.callback_query(F.data.startswith("token_"))
async def token_pay_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    packs = {'50': (10, 50), '200': (30, 200), '500': (60, 500), '1000': (120, 1000), '2500': (250, 2500)}
    pack_type = callback.data.replace("token_", "")
    if pack_type not in packs:
        await safe_answer(callback, "❌ Неверный пакет", show_alert=True)
        return
    stars, tokens = packs[pack_type]
    payload = secrets.token_hex(16)
    create_payment(user_id, stars, payload, "tokens")
    await callback.bot.send_invoice(
        chat_id=user_id, title=f"📦 {tokens} токенов",
        description=f"{tokens} токенов = {tokens//10} картинок",
        payload=payload, provider_token=PROVIDER_TOKEN, currency="XTR",
        prices=[LabeledPrice(label=f"{tokens} токенов", amount=stars)],
        start_parameter="buy_tokens"
    )
    await safe_answer(callback)

@router.callback_query(F.data.startswith("sub_"))
async def subscribe_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    plan = callback.data.replace("sub_", "")
    if plan == "premium":
        stars, plan_name = 150, "💎 Премиум"
    elif plan == "premium_plus":
        stars, plan_name = 300, "👑 Премиум+"
    else:
        await safe_answer(callback, "❌ Неверный тариф", show_alert=True)
        return
    payload = secrets.token_hex(16)
    create_payment(user_id, stars, payload, f"subscription_{plan}")
    await callback.bot.send_invoice(
        chat_id=user_id, title=plan_name,
        description="Подписка на 30 дней",
        payload=payload, provider_token=PROVIDER_TOKEN, currency="XTR",
        prices=[LabeledPrice(label=plan_name, amount=stars)],
        start_parameter="subscribe"
    )
    await safe_answer(callback)

@router.message(F.successful_payment)
async def payment_success(message: types.Message):
    payload = message.successful_payment.invoice_payload
    payment = complete_payment(payload)
    if payment:
        stars, plan = payment['stars_amount'], payment['plan']
        if plan.startswith("subscription_"):
            plan_type = plan.replace("subscription_", "")
            add_premium(message.from_user.id, 30, plan_type, True)
            await message.answer(f"✅ Подписка {plan_type} активирована на 30 дней!", reply_markup=main_menu())
            return
        if plan == "tokens":
            packs = {10: 50, 30: 200, 60: 500, 120: 1000, 250: 2500}
            tokens = packs.get(stars, 0)
            if tokens > 0:
                add_tokens(message.from_user.id, tokens)
                await message.answer(f"✅ +{tokens} токенов!", reply_markup=main_menu())
            else:
                await message.answer("❌ Ошибка")
        else:
            await message.answer("❌ Ошибка")
    else:
        await message.answer("❌ Ошибка")

@router.callback_query(F.data == "contact_admin")
async def contact_cb(callback: types.CallbackQuery):
    user_pages[callback.from_user.id] = {"state": "waiting_contact"}
    await callback.message.edit_text("📩 Напиши сообщение", reply_markup=main_menu())
    await safe_answer(callback)

@router.callback_query(F.data == "back_to_main")
async def back_main_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    tokens = get_tokens(user_id)
    name = get_user_name(user_id) or "друг"
    await callback.message.edit_text(f"✨ **Vertex AI**\n\n👋 Привет, {name}!\n💰 Токенов: {tokens}", reply_markup=main_menu())
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

@router.callback_query(F.data.startswith("edit_"))
async def edit_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    image_id = int(callback.data.replace("edit_", ""))
    image = get_image_by_id(image_id)
    if not image:
        await safe_answer(callback, "❌ Картинка не найдена", show_alert=True)
        return
    user_pages[user_id] = {"state": "waiting_edit", "image_id": image_id}
    await callback.message.answer("✏️ Напиши, что изменить:", reply_markup=edit_in_progress_kb())
    await safe_answer(callback)

@router.callback_query(F.data == "cancel_edit")
async def cancel_edit_cb(callback: types.CallbackQuery):
    user_pages.pop(callback.from_user.id, None)
    await callback.message.edit_text("✅ Отменено", reply_markup=main_menu())
    await safe_answer(callback)


# ============================================================================
# ============================ АДМИН-ФУНКЦИИ ===============================
# ============================================================================

@router.callback_query(F.data == "a_stats")
async def a_stats_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    total, total_tokens, total_requests, total_images, premium_users = get_stats()
    await callback.message.edit_text(
        f"📊 **СТАТИСТИКА**\n\n👥 Всего: {total}\n💎 Премиум: {premium_users}\n💰 Токенов: {total_tokens}\n📝 Запросов: {total_requests}\n🖼️ Картинок: {total_images}",
        reply_markup=admin_kb()
    )
    await safe_answer(callback)

@router.callback_query(F.data == "a_model_stats")
async def a_model_stats_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    total = sum(model_stats.values())
    text = "📈 **МОДЕЛИ**\n\n" + (f"Всего: {total}\n\n" if total > 0 else "❌ Пока нет статистики.")
    for key, count in model_stats.items():
        if count > 0:
            model = IMAGE_MODELS[key]
            text += f"{model['name']}: {count} ({round(count/total*100,1)}%)\n"
    await callback.message.edit_text(text, reply_markup=admin_kb())
    await safe_answer(callback)

@router.callback_query(F.data == "a_users")
async def a_users_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, tokens, is_blocked FROM users WHERE user_id != 8676871187 ORDER BY tokens DESC LIMIT 20")
    users = cursor.fetchall()
    conn.close()
    text = "👥 **Топ**\n\n"
    for u in users:
        status = "⛔" if u['is_blocked'] == 1 else "✅"
        name = u['username'] if u['username'] and u['username'] != str(u['user_id']) else "Без имени"
        text += f"{status} {name}: {u['tokens']} токенов\n"
    await callback.message.edit_text(text[:4000], reply_markup=admin_kb())
    await safe_answer(callback)

@router.callback_query(F.data == "a_give_tokens")
async def a_give_tokens_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    user_pages[callback.from_user.id] = {"state": "waiting_give_tokens"}
    await callback.message.edit_text("⭐ **Раздать токены**\n\nФормат: `ID | кол-во` или `всем | кол-во`", reply_markup=admin_kb())
    await safe_answer(callback)

@router.callback_query(F.data == "a_broadcast")
async def a_broadcast_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    user_pages[callback.from_user.id] = {"state": "waiting_broadcast"}
    await callback.message.edit_text("📢 **Рассылка**\n\nВведите текст.", reply_markup=admin_kb())
    await safe_answer(callback)

@router.callback_query(F.data == "a_block")
async def a_block_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, is_blocked FROM users WHERE user_id != 8676871187 LIMIT 20")
    users = cursor.fetchall()
    conn.close()
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for u in users:
        name = u['username'] if u['username'] and u['username'] != str(u['user_id']) else str(u['user_id'])
        status = "✅" if u['is_blocked'] == 0 else "⛔"
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{status} {name}", callback_data=f"block_user_{u['user_id']}")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])
    await callback.message.edit_text("🚫 **Блокировка**", reply_markup=kb)
    await safe_answer(callback)

@router.callback_query(F.data.startswith("block_user_"))
async def block_user_action(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    user_id = int(callback.data.replace("block_user_", ""))
    user = get_user(user_id)
    if not user:
        await safe_answer(callback, "❌ Не найден", show_alert=True)
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
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, username, text, date FROM messages_to_admin ORDER BY date DESC LIMIT 20")
    msgs = cursor.fetchall()
    conn.close()
    if not msgs:
        await callback.message.edit_text("📭 Нет обращений.", reply_markup=admin_kb())
        await safe_answer(callback)
        return
    text = "📩 **Обращения**\n\n"
    for m in msgs:
        name = m['username'] if m['username'] and m['username'] != str(m['user_id']) else str(m['user_id'])
        text += f"👤 {name}: {m['text'][:50]}\n🕐 {m['date'][:16]}\n\n"
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
    if not os.path.exists('data/repsolver.db'):
        await callback.message.edit_text("❌ БД не найдена", reply_markup=admin_kb())
        await safe_answer(callback)
        return
    try:
        await callback.message.delete()
        await callback.message.answer_document(
            BufferedInputFile(open('data/repsolver.db', 'rb').read(), filename="repsolver.db"),
            caption="📁 База данных", reply_markup=admin_kb()
        )
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}", reply_markup=admin_kb())
    await safe_answer(callback)

@router.callback_query(F.data == "a_restore_github")
async def restore_github_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    result = GitHubBackup().restore_latest_backup()
    await callback.message.edit_text("✅ БД восстановлена!" if result else "❌ Ошибка", reply_markup=admin_kb())
    await safe_answer(callback)

@router.callback_query(F.data == "a_edit_prices")
async def a_edit_prices_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for key, model in IMAGE_MODELS.items():
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{model['name']} — {model['price']} токенов", callback_data=f"edit_price_{key}")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])
    await callback.message.edit_text("💰 **Цены**\n\nВыбери модель:", reply_markup=kb)
    await safe_answer(callback)

@router.callback_query(F.data.startswith("edit_price_"))
async def edit_price_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    model_key = callback.data.replace("edit_price_", "")
    user_pages[callback.from_user.id] = {"state": "waiting_price", "model": model_key}
    await callback.message.edit_text(f"💰 Введи новую цену для {IMAGE_MODELS[model_key]['name']}:", reply_markup=admin_kb())
    await safe_answer(callback)

@router.callback_query(F.data == "a_promocodes")
async def a_promocodes_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать", callback_data="a_create_promo")],
        [InlineKeyboardButton(text="📋 Список", callback_data="a_list_promos")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    await callback.message.edit_text("🎫 **Промокоды**", reply_markup=kb)
    await safe_answer(callback)

@router.callback_query(F.data == "a_create_promo")
async def a_create_promo_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    user_pages[callback.from_user.id] = {"state": "waiting_promo_code"}
    await callback.message.edit_text("🎫 **Создание**\n\nФормат: `код | токены | дни`\nПример: `WELCOME | 100 | 30`", reply_markup=admin_kb())
    await safe_answer(callback)

@router.callback_query(F.data == "a_list_promos")
async def a_list_promos_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM promocodes ORDER BY created_at DESC")
    promos = cursor.fetchall()
    conn.close()
    if not promos:
        await callback.message.edit_text("📋 Нет промокодов", reply_markup=admin_kb())
        await safe_answer(callback)
        return
    text = "📋 **Промокоды**\n\n"
    for p in promos:
        text += f"🔹 `{p['code']}` +{p['bonus_tokens']} токенов, использован {p['used']}/{p['max_uses']}, до {p['expires_at'][:10]}\n"
    await callback.message.edit_text(text[:4000], reply_markup=admin_kb())
    await safe_answer(callback)

@router.callback_query(F.data == "a_stars_balance")
async def a_stars_balance_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    try:
        balance = await callback.bot.get_my_star_balance()
        byn = balance * 0.013
        rub = balance * 0.45
        await callback.message.edit_text(
            f"⭐ **Баланс Stars**\n\nНа счету: {balance} Stars\n💵 ≈ {byn:.2f} BYN ≈ {rub:.2f} ₽\n💡 Мин. вывод: 1000 Stars",
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
