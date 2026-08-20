from aiogram import Router, types, F
from database.db import *
from ai.client import solve_problem
from . import helpers
from .image import generate_image
import logging, json, re, os, requests

router = Router()
logger = logging.getLogger(__name__)

API_KEY = os.getenv('OPENAI_API_KEY')
PROMPT_MODEL = "gpt-4.1-nano"

async def ai_analyze_intent(user_id, text):
    """Анализ запроса через GPT"""
    if not API_KEY:
        logger.error("❌ API_KEY отсутствует")
        return 'chat', {}

    system_prompt = """Ты — ИИ-ассистент бота. Определи, что хочет пользователь.

Верни ТОЛЬКО JSON:
{"action": "действие", "params": {"prompt": "текст"}}

Действия:
- generate_image: пользователь хочет создать картинку
- edit_image: пользователь хочет изменить картинку
- show_prices: пользователь спрашивает о ценах
- show_balance: пользователь спрашивает баланс
- show_referral: пользователь спрашивает о рефералах
- chat: обычный разговор"""

    try:
        logger.info(f"🧠 [{user_id}] Анализ запроса через GPT: {text[:50]}...")
        
        resp = requests.post(
            "https://openai.bothub.chat/v1/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "model": PROMPT_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Запрос: {text}"}
                ],
                "max_tokens": 150,
                "temperature": 0.1
            },
            timeout=15
        )
        
        if resp.status_code == 200:
            result = resp.json().get('choices', [{}])[0].get('message', {}).get('content', '{}')
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                action = data.get('action', 'chat')
                params = data.get('params', {})
                logger.info(f"✅ [{user_id}] GPT определил: {action}")
                return action, params
        else:
            logger.error(f"❌ [{user_id}] Ошибка GPT: {resp.status_code}")
            
    except Exception as e:
        logger.error(f"❌ [{user_id}] Ошибка анализа: {e}")
    
    return 'chat', {}

@router.message(F.text)
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # === СНАЧАЛА ПРОВЕРЯЕМ СОСТОЯНИЯ (АДМИН-ВВОД) ===
    state = helpers.user_pages.get(user_id, {})
    
    # Если пользователь в админ-режиме — не анализируем через GPT
    if state.get("state") in [
        "waiting_broadcast",      # Рассылка
        "waiting_block_user",     # Блокировка
        "waiting_contact",        # Поддержка
        "waiting_give_tokens",    # Раздача токенов
        "waiting_price",          # Изменение цен
        "waiting_promo_code",     # Создание промокода
        "waiting_edit"            # Правка картинки
    ]:
        logger.info(f"📌 [{user_id}] Админ-ввод: {state.get('state')}")
        from .admin import handle_admin_input
        await handle_admin_input(message)
        return
    
    # Если пользователь вводит промокод для активации
    if state.get("state") == "waiting_promo_use":
        success, msg = use_promocode(text.upper(), user_id)
        await message.answer(msg, reply_markup=helpers.main_menu())
        helpers.user_pages.pop(user_id, None)
        return
    
    # Если пользователь вводит имя
    if state.get("state") == "waiting_name":
        from .start import start_cmd
        set_user_name(user_id, text)
        helpers.user_pages.pop(user_id, None)
        await message.answer(f"✅ Отлично! Я запомнил тебя.")
        await start_cmd(message)
        return
    
    # === АНАЛИЗ ЧЕРЕЗ GPT ДЛЯ ОБЫЧНЫХ ЗАПРОСОВ ===
    action, params = await ai_analyze_intent(user_id, text)
    
    if action == 'generate_image':
        prompt = params.get('prompt', text)
        await generate_image(message, prompt)
        
    elif action == 'edit_image':
        last_img = get_last_image(user_id)
        if last_img:
            prompt = params.get('prompt', text)
            full_prompt = f"{last_img.get('prompt', '')}, {prompt}"
            await generate_image(message, full_prompt)
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

async def generate_text(message: types.Message):
    user_id = message.from_user.id
    if not can_request_text(user_id):
        await message.answer("🔒 Лимит запросов исчерпан! Завтра будет новый день.")
        return

    status_msg = await message.answer("🤔 Думаю...")
    try:
        answer = solve_problem(message.text, "chat", False)
        add_text_request(user_id)
        used, max_req = get_text_requests(user_id)
        add_to_context(user_id, message.text)
        await status_msg.edit_text(f"🧠 {answer}\n\n📝 Осталось: {max_req - used}/{max_req}")
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def send_price_info(message: types.Message):
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
    await message.answer(text, reply_markup=helpers.main_menu())

async def send_referral_info(message: types.Message):
    user_id = message.from_user.id
    count = get_referral_count(user_id)
    link = f"https://t.me/Vertex1bot?start={user_id}"
    text = (
        "👥 **Рефералы**\n\n"
        f"👤 Приглашено: {count}\n"
        f"🎁 Бонус: +20 токенов за друга\n\n"
        f"🔗 Твоя ссылка:\n{link}"
    )
    await message.answer(text, reply_markup=helpers.main_menu())

async def balance_cmd(message: types.Message):
    user_id = message.from_user.id
    tokens = get_tokens(user_id)
    used, max_req = get_text_requests(user_id)
    await message.answer(
        f"💰 **Баланс**\n\n"
        f"🪙 Токенов: {tokens}\n"
        f"🖼️ Хватит на: {tokens // 10} картинок\n"
        f"📝 Текст: {used}/{max_req} запросов сегодня",
        reply_markup=helpers.main_menu()
    )
