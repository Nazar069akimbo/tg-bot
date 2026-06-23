from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import get_user, can_generate_image, add_image_request, get_user_plan
from keyboards import main_menu
import logging
import requests
import os
import asyncio

router = Router()
logger = logging.getLogger(__name__)

BOTHUB_API_KEY = os.getenv('BOTHUB_API_KEY')

# Все возможные ключевые слова для картинок
IMAGE_KEYWORDS = [
    "нарисуй", "сгенерируй", "картинку", "изображение", "покажи",
    "сделай", "draw", "image", "создай", "генерация", "рисунок",
    "картина", "иллюстрация", "арт", "фон", "обои", "пейзаж",
    "портрет", "нарисовать", "изобрази", "сгенерировать",
    "вид на", "море", "город", "закат", "рассвет", "горы",
    "лес", "океан", "небо", "облака", "девушка", "парень",
    "животное", "кот", "собака", "машина", "дом", "природа"
]

@router.message(Command("image"))
async def image_cmd(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user:
        await message.answer("👋 Напишите /start для регистрации")
        return
    
    plan = get_user_plan(user_id)
    can_gen, remaining = can_generate_image(user_id)
    
    await message.answer(
        f"🖼️ **Генерация картинок**\n\n"
        f"Просто напиши текст, и я нарисую картинку!\n\n"
        f"📝 Примеры:\n"
        f"• кот в космосе\n"
        f"• горы и закат\n"
        f"• киберпанк город\n\n"
        f"📊 Твой план: {plan.upper()}\n"
        f"🎯 Осталось картинок: {'∞' if not can_gen else remaining}"
    )

@router.message(F.text)
async def handle_message(message: types.Message):
    if not message.text or message.text.startswith("/"):
        return
    
    # Проверяем, админ ли это в режиме поиска
    try:
        from handlers.admin_handler import user_pages
        state = user_pages.get(message.from_user.id, {})
        if state.get("state") in ["waiting_user_search", "waiting_admin_message"]:
            return
    except:
        pass
    
    user = get_user(message.from_user.id)
    if not user:
        return
    
    text = message.text.lower()
    
    # ============ ПРОВЕРКА НА КАРТИНКУ ============
    is_image = False
    
    # 1. Если сообщение начинается с ключевых слов
    for kw in ["нарисуй", "сгенерируй", "создай", "нарисовать", "изобрази", "draw", "image", "картинку", "покажи"]:
        if text.startswith(kw) or f" {kw} " in text:
            is_image = True
            break
    
    # 2. Если запрос короткий (до 30 символов) — скорее всего хотят картинку
    if len(text) < 30 and not any(q in text for q in ["что", "как", "почему", "кто", "где", "когда"]):
        is_image = True
    
    # 3. Если есть слово "картинка", "изображение", "рисунок"
    if any(kw in text for kw in ["картинк", "изображени", "рисунк", "арт", "пейзаж"]):
        is_image = True
    
    if is_image:
        await generate_image(message)
        return
    
    # ============ ТЕКСТОВЫЙ ЗАПРОС ============
    ok, remaining = can_request(message.from_user.id)
    if not ok:
        await message.answer(
            f"🔒 Лимит исчерпан!\n\n"
            f"Бесплатно: 10 запросов/день\n"
            f"Осталось: 0\n\n"
            f"💎 Купите Premium: /subscribe"
        )
        return
    
    premium = is_premium(message.from_user.id)
    status_msg = await message.answer("🤔 Думаю...")
    
    answer = solve_problem(message.text, "chat", premium)
    add_request(message.from_user.id)
    
    remaining_after = remaining - 1 if not premium else "∞"
    result_text = f"🧠 {answer}\n\n"
    result_text += f"🎯 Осталось запросов: {remaining_after}" if not premium else "💎 Premium — безлимит"
    
    await status_msg.edit_text(result_text)

async def generate_image(message: types.Message):
    user_id = message.from_user.id
    
    can_gen, remaining = can_generate_image(user_id)
    if not can_gen:
        await message.answer(
            f"❌ Лимит картинок исчерпан!\n\n"
            f"🎯 Осталось: {remaining}\n"
            f"💎 Купи Premium для большего количества: /subscribe"
        )
        return
    
    status_msg = await message.answer("🎨 Генерирую картинку... 0%")
    
    try:
        prompt = message.text
        
        # Прогресс
        progress = [10, 25, 45, 60, 75, 90]
        for p in progress:
            await asyncio.sleep(0.4)
            try:
                await status_msg.edit_text(f"🎨 Генерирую картинку... {p}%")
            except:
                pass
        
        url = "https://api.bothub.chat/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {BOTHUB_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "gpt-image",
            "prompt": prompt,
            "n": 1,
            "size": "512x512"
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            image_url = result.get('data', [{}])[0].get('url')
            
            if image_url:
                await status_msg.edit_text("🎨 Генерирую картинку... 100% ✅")
                await asyncio.sleep(0.3)
                
                await message.answer_photo(
                    photo=image_url,
                    caption=f"🖼️ **Твоя картинка**\n📝 Запрос: {prompt[:100]}{'...' if len(prompt) > 100 else ''}"
                )
                add_image_request(user_id)
                await status_msg.delete()
            else:
                await status_msg.edit_text("❌ Не удалось сгенерировать картинку. Попробуй другой запрос.")
        else:
            await status_msg.edit_text("❌ Ошибка генерации. Попробуй позже.")
            
    except Exception as e:
        logger.error(f"Image error: {e}")
        await status_msg.edit_text("❌ Ошибка. Попробуй позже.")
