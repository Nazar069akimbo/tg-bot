import logging
import asyncio
import os
import sys
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from database.db import *
from backup import GitHubBackup

# ===== НАСТРОЙКА ЛОГГИРОВАНИЯ =====
logger = logging.getLogger(__name__)

# ===== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ =====
router = Router()
user_modes = {}
user_pages = {}
ADMIN_CODE = "30121979"

# ===== ДЕКОРАТОР ЗАЩИТЫ ОТ ОШИБОК =====
def safe_handler(func):
    """Защищает обработчик от любых ошибок — бот не падает"""
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except TelegramBadRequest as e:
            logger.warning(f"⚠️ Telegram ошибка: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
            try:
                # Пытаемся уведомить админа
                admin_id = int(os.getenv('ADMIN_ID', 6957852385))
                await bot.send_message(admin_id, f"⚠️ Ошибка в обработчике:\n{func.__name__}\n{str(e)[:200]}")
            except:
                pass
            return None
    return wrapper

# ===== ИНИЦИАЛИЗАЦИЯ =====
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

# ===== КЛАВИАТУРЫ =====
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧠 Текст", callback_data="mode_text"), InlineKeyboardButton(text="🖼️ Картинка", callback_data="mode_image")],
        [InlineKeyboardButton(text="📅 Бонус дня", callback_data="daily_bonus"), InlineKeyboardButton(text="💎 Premium", callback_data="premium")],
        [InlineKeyboardButton(text="👥 Рефералы", callback_data="referral"), InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats"), InlineKeyboardButton(text="📩 Поддержка", callback_data="contact_admin")],
        [InlineKeyboardButton(text="🏆 Рейтинг", callback_data="leaderboard"), InlineKeyboardButton(text="🛡️ Админ", callback_data="admin_panel")]
    ])

def admin_kb():
    new_messages = get_messages_count()
    badge = f" ({new_messages})" if new_messages > 0 else ""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="a_stats"), InlineKeyboardButton(text="👥 Пользователи", callback_data="a_users")],
        [InlineKeyboardButton(text="💎 Выдать Premium", callback_data="a_give_premium"), InlineKeyboardButton(text="🔄 Сменить тариф", callback_data="a_change_plan")],
        [InlineKeyboardButton(text=f"📩 Обращения{badge}", callback_data="a_messages"), InlineKeyboardButton(text="🚫 Блокировка", callback_data="a_block")],
        [InlineKeyboardButton(text="⚙️ Тарифы", callback_data="a_plans"), InlineKeyboardButton(text="📢 Рассылка", callback_data="a_broadcast")],
        [InlineKeyboardButton(text="💾 Бэкап", callback_data="a_backup"), InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

# ===== КОМАНДЫ =====
@router.message(Command("start"))
@safe_handler
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

# ===== ОБРАБОТКА ТЕКСТА =====
@router.message(F.text)
@safe_handler
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
    
    if state.get("state") in ["waiting_plan_edit", "waiting_premium_user", "waiting_broadcast", "waiting_block_user", "waiting_contact", "waiting_reply", "waiting_change_plan"]:
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

@safe_handler
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
        logger.error(f"Ошибка generate_text: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

@safe_handler
async def generate_image(message: types.Message):
    user_id = message.from_user.id
    API_KEY = os.getenv('OPENAI_API_KEY')
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
        import requests
        user_prompt = message.text
        IMAGE_MODEL = "flux-schnell"
        PROMPT_MODEL = "gpt-4.1-nano"
        
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
                import requests as req
                img_data = req.get(img_url, timeout=30)
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
        logger.error(f"Ошибка generate_image: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

# ===== CALLBACK'и =====
@router.callback_query(F.data.in_(["mode_text", "mode_image"]))
@safe_handler
async def set_mode(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    mode = callback.data.replace("mode_", "")
    user_modes[user_id] = mode
    await callback.answer(f"✅ Режим: {'🧠 Текст' if mode == 'text' else '🖼️ Картинка'}", show_alert=True)
    await callback.message.edit_text(f"{'🧠 Текст' if mode == 'text' else '🖼️ Картинка'}\n\nГотов к работе!", reply_markup=main_menu())

@router.callback_query(F.data == "daily_bonus")
@safe_handler
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
@safe_handler
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

# ===== АДМИН-ФУНКЦИИ =====
@router.message(Command("admin"))
@safe_handler
async def admin_cmd(message: types.Message):
    if is_admin(message.from_user.id):
        await message.answer("🛡️ **АДМИН-ПАНЕЛЬ**", reply_markup=admin_kb())
    else:
        await message.answer("🔐 Введите код: /admin_code 30121979")

@router.message(Command("admin_code"))
@safe_handler
async def admin_code_cmd(message: types.Message):
    args = message.text.split() if message.text else []
    if len(args) > 1 and args[1] == ADMIN_CODE:
        add_admin(message.from_user.id)
        await message.answer("✅ Вы админ!", reply_markup=admin_kb())

# ===== АДМИН-CALLBACK'и =====
@router.callback_query(F.data == "admin_panel")
@safe_handler
async def admin_panel_cb(callback: types.CallbackQuery):
    if is_admin(callback.from_user.id):
        await callback.message.edit_text("🛡️ **АДМИН-ПАНЕЛЬ**", reply_markup=admin_kb())
        await callback.answer()
    else:
        await callback.answer("⛔ Нет доступа", show_alert=True)

@router.callback_query(F.data == "a_stats")
@safe_handler
async def a_stats_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    total, prem, req, images, paid = get_stats()
    await callback.message.edit_text(
        f"📊 **СТАТИСТИКА**\n\n"
        f"👥 Всего: {total}\n"
        f"💎 Premium: {prem}\n"
        f"💰 Оплатили: {paid}\n"
        f"📝 Запросов: {req}\n"
        f"🖼️ Картинок: {images}",
        reply_markup=admin_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "a_users")
@safe_handler
async def a_users_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, total_requests, image_requests, plan, is_blocked FROM users ORDER BY user_id LIMIT 20")
        users = cursor.fetchall()
    if not users:
        await callback.message.edit_text("👥 Нет пользователей", reply_markup=admin_kb())
        await callback.answer()
        return
    text = "👥 **Пользователи**\n\n"
    for u in users:
        status_text = "⛔" if u['is_blocked'] == 1 else "✅"
        plan_emoji = {"basic": "🔴", "premium": "💎", "premium_deluxe": "👑"}.get(u['plan'], "🔴")
        name = u['username'] if u['username'] and u['username'] != str(u['user_id']) else "Без имени"
        text += f"{status_text} {plan_emoji} **{name}** (ID: {u['user_id']})\n"
        text += f"   📝{u['total_requests']} | 🖼️{u['image_requests']}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    try:
        await callback.message.edit_text(text[:4000], reply_markup=kb)
    except:
        await callback.message.answer(text[:4000], reply_markup=kb)
    await callback.answer()

# ===== ОБРАБОТЧИК ВВОДА АДМИНА =====
@safe_handler
async def handle_admin_input(message: types.Message):
    user_id = message.from_user.id
    state = user_pages.get(user_id, {})
    
    if message.text == "/cancel":
        user_pages.pop(user_id, None)
        await message.answer("✅ Отменено", reply_markup=admin_kb())
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

# ===== ОСТАЛЬНЫЕ КОМАНДЫ =====
@router.message(Command("cancel"))
@safe_handler
async def cancel_cmd(message: types.Message):
    user_pages.pop(message.from_user.id, None)
    await message.answer("✅ Отменено", reply_markup=main_menu())

# ===== ЗАЩИТА ОТ НЕИЗВЕСТНЫХ CALLBACK'ов =====
@router.callback_query()
@safe_handler
async def unknown_callback(callback: types.CallbackQuery):
    await callback.answer("⚠️ Действие временно недоступно", show_alert=True)
