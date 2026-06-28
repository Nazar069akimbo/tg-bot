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

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🧠 Текст", callback_data="mode_text"),
            InlineKeyboardButton(text="🖼️ Картинка", callback_data="mode_image")
        ],
        [
            InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="stats")
        ],
        [
            InlineKeyboardButton(text="👥 Рефералы", callback_data="referral"),
            InlineKeyboardButton(text="💎 Premium", callback_data="premium")
        ],
        [
            InlineKeyboardButton(text="📩 Админу", callback_data="contact_admin"),
            InlineKeyboardButton(text="❓ Помощь", callback_data="help")
        ],
        [
            InlineKeyboardButton(text="🏆 Рейтинг", callback_data="leaderboard"),
            InlineKeyboardButton(text="🛡️ Админ", callback_data="admin_panel")
        ]
    ])

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="a_stats"),
            InlineKeyboardButton(text="👥 Пользователи", callback_data="a_users")
        ],
        [
            InlineKeyboardButton(text="📢 Рассылка", callback_data="a_broadcast"),
            InlineKeyboardButton(text="💎 Выдать Premium", callback_data="a_give_premium")
        ],
        [
            InlineKeyboardButton(text="💾 Бэкап", callback_data="a_backup"),
            InlineKeyboardButton(text="⚙️ Лимиты", callback_data="a_limits")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")
        ]
    ])

@router.message(Command("start"))
async def start_cmd(message: types.Message):
    logger.info(f"📱 Start command from {message.from_user.id}")
    user_id = message.from_user.id
    if not get_user(user_id):
        create_user(user_id, message.from_user.username or "")
        args = message.text.split()
        if len(args) > 1 and args[1].isdigit() and int(args[1]) != user_id:
            add_referral(int(args[1]), user_id)
            await message.answer("👤 Вы приглашены! Реферер +5 запросов.")
    await message.answer("🤖 **Vertex AI**\n\n🧠 ИИ в Telegram!\n✅ 10 запросов/день\n💎 Premium: безлимит\n👥 Приведи друга → +5 запросов\n\nПросто напиши вопрос!", reply_markup=main_menu())

@router.message(Command("stats"))
async def stats_cmd(message: types.Message):
    logger.info(f"📊 Stats from {message.from_user.id}")
    user = get_user(message.from_user.id)
    if not user: 
        return await message.answer("❌ Сначала нажми /start")
    
    ok, rem = can_request(message.from_user.id)
    used, limit, prem = get_image_stats(message.from_user.id)
    trial = get_trial_remaining(message.from_user.id)
    
    text = f"📊 **Статистика**\n\n"
    text += f"📝 Текстовых запросов: {rem if not prem else '∞'}\n"
    text += f"🖼️ Картинок сегодня: {used}/{limit}\n"
    if trial > 0 and not prem:
        text += f"🎁 Пробный период: {trial} картинок осталось\n"
    text += f"💎 Статус: {'💎 Premium' if prem else '🔴 Бесплатный'}\n"
    text += f"🎯 Режим: {'🧠 Текст' if user_modes.get(message.from_user.id, 'text') == 'text' else '🖼️ Картинка'}"
    
    await message.answer(text, reply_markup=main_menu())

@router.message(Command("profile"))
async def profile_cmd(message: types.Message):
    logger.info(f"👤 Profile from {message.from_user.id}")
    user = get_user(message.from_user.id)
    if not user: 
        return await message.answer("❌ Сначала нажми /start")
    
    cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (message.from_user.id,))
    refs = cursor.fetchone()[0] or 0
    used, limit, prem = get_image_stats(message.from_user.id)
    plan = get_user_plan(message.from_user.id)
    
    text = f"👤 **Профиль**\n\n"
    text += f"🆔 ID: {user[0]}\n"
    text += f"📆 Регистрация: {user[2][:10] if user[2] else 'Нет'}\n"
    text += f"📊 Запросов: {user[5] or 0}\n"
    text += f"👥 Приглашено: {refs}\n"
    text += f"💎 Premium: {'✅ Активен' if prem else '❌ Нет'}\n"
    text += f"📊 План: {plan.upper()}\n"
    text += f"🖼️ Картинки сегодня: {used}/{limit}"
    
    await message.answer(text, reply_markup=main_menu())

@router.message(Command("subscribe"))
async def subscribe_cmd(message: types.Message):
    logger.info(f"💎 Subscribe from {message.from_user.id}")
    await message.answer("💎 **Premium**\n\n1 мес — 49⭐\n3 мес — 129⭐\n6 мес — 249⭐\n12 мес — 449⭐", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐ 1 мес 49⭐", callback_data="pay_1"),
            InlineKeyboardButton(text="⭐ 3 мес 129⭐", callback_data="pay_3")
        ],
        [
            InlineKeyboardButton(text="⭐ 6 мес 249⭐", callback_data="pay_6"),
            InlineKeyboardButton(text="⭐ 12 мес 449⭐", callback_data="pay_12")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")
        ]
    ]))

@router.message(Command("referral"))
async def referral_cmd(message: types.Message):
    logger.info(f"👥 Referral from {message.from_user.id}")
    user_id = message.from_user.id
    if not get_user(user_id): return await message.answer("❌ /start")
    cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
    count = cursor.fetchone()[0] or 0
    link = f"https://t.me/Vertex1bot?start={user_id}"
    await message.answer(f"👥 **Рефералы**\n\nПриглашено: {count}\nБонус: +5 запросов\n\n🔗 {link}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📤 Поделиться", url=f"https://t.me/share/url?url={link}&text=🤖 Присоединяйся!")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")
        ]
    ]))

# ГЛАВНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ - ПРОСТЕЙШАЯ ВЕРСИЯ ДЛЯ ТЕСТА
@router.message(F.text)
async def handle_message(message: types.Message):
    # Логируем ВСЕ сообщения
    logger.info(f"📨 ПОЛУЧЕНО СООБЩЕНИЕ от {message.from_user.id}: {message.text[:50]}")
    
    # Пропускаем команды
    if message.text.startswith("/"):
        logger.info("⏭️ Это команда, пропускаем")
        return
    
    # Проверяем регистрацию
    if not get_user(message.from_user.id):
        logger.info("❌ Пользователь не зарегистрирован")
        await message.answer("👋 Нажми /start", reply_markup=main_menu())
        return
    
    # Получаем режим
    mode = user_modes.get(message.from_user.id, "text")
    logger.info(f"🎯 Режим пользователя: {mode}")
    
    # Отправляем тестовое сообщение
    await message.answer(f"✅ Я получил твое сообщение!\nРежим: {mode}\nТекст: {message.text[:50]}...")
    
    # Если режим "картинка" - пробуем сгенерировать
    if mode == "image":
        await generate_image(message)
    else:
        await generate_text(message)

async def generate_text(message: types.Message):
    logger.info("📝 Начинаем генерацию текста")
    ok, remaining = can_request(message.from_user.id)
    if not ok:
        await message.answer("🔒 Лимит исчерпан! Купи Premium: /subscribe")
        return
    
    premium = is_premium(message.from_user.id)
    status_msg = await message.answer("🤔 Думаю...")
    
    try:
        answer = solve_problem(message.text, "chat", premium)
        add_request(message.from_user.id)
        
        remaining_after = remaining - 1 if not premium else "∞"
        result_text = f"🧠 {answer}\n\n"
        if not premium:
            result_text += f"🎯 Осталось запросов: {remaining_after}"
        else:
            result_text += "💎 Premium — безлимит"
        
        await status_msg.edit_text(result_text)
        logger.info("✅ Текст сгенерирован")
    except Exception as e:
        logger.error(f"❌ Ошибка текста: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def generate_image(message: types.Message):
    logger.info("🎨 НАЧАЛО ГЕНЕРАЦИИ КАРТИНКИ")
    user_id = message.from_user.id
    
    # Проверяем API ключ
    if not API_KEY:
        logger.error("❌ OPENAI_API_KEY не найден!")
        await message.answer("❌ API ключ не настроен. Обратитесь к администратору.")
        return
    
    # Получаем информацию о пользователе
    trial_remaining = get_trial_remaining(user_id)
    used, limit, prem = get_image_stats(user_id)
    
    logger.info(f"📊 Статистика: used={used}, limit={limit}, prem={prem}, trial={trial_remaining}")
    
    # Проверяем лимиты
    if prem:
        can_gen = used < limit
    elif trial_remaining > 0:
        can_gen = True
        limit = 5
    else:
        can_gen, remaining = can_generate_image(user_id)
    
    if not can_gen:
        await message.answer(
            f"❌ **Лимит картинок исчерпан!**\n\n"
            f"📊 Использовано: {used}/{limit}\n"
            f"⏳ Лимит обновится завтра\n\n"
            f"💎 Купи Premium: /subscribe"
        )
        return
    
    status_msg = await message.answer("🎨 Генерирую картинку...")
    
    try:
        user_prompt = message.text
        
        # Генерация промпта
        logger.info("🔄 Создаю промпт...")
        prompt_url = "https://openai.bothub.chat/v1/chat/completions"
        prompt_headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        
        prompt_data = {
            "model": PROMPT_MODEL,
            "messages": [
                {"role": "system", "content": "You are a professional prompt engineer. Convert the user's request into a detailed English prompt for Flux/Stable Diffusion. Rules: 1. ALWAYS respond ONLY in English 2. Prompt should be 30-60 words 3. Add details: style, lighting, mood, colors 4. Use quality keywords: photorealistic, 8k, highly detailed. Only the prompt, no explanations!"},
                {"role": "user", "content": f"Create a prompt for: {user_prompt}"}
            ],
            "max_tokens": 200,
            "temperature": 0.7
        }
        
        prompt_response = requests.post(prompt_url, headers=prompt_headers, json=prompt_data, timeout=30)
        logger.info(f"📡 Ответ промпта: {prompt_response.status_code}")
        
        if prompt_response.status_code == 200:
            prompt_result = prompt_response.json()
            enhanced_prompt = prompt_result.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
            if enhanced_prompt.startswith('"') and enhanced_prompt.endswith('"'):
                enhanced_prompt = enhanced_prompt[1:-1]
            logger.info(f"📝 Промпт: {enhanced_prompt[:100]}...")
        else:
            enhanced_prompt = user_prompt
            logger.warning("⚠️ Не удалось создать промпт")
        
        await status_msg.edit_text(f"🎨 Генерирую картинку...")
        
        # Прогресс
        for p in [10, 25, 45, 60, 75, 90]:
            await asyncio.sleep(0.2)
            try:
                await status_msg.edit_text(f"🎨 Генерирую картинку... {p}%")
            except:
                pass
        
        # Генерация картинки
        url = "https://bothub.chat/api/v2/replicate/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": IMAGE_MODEL,
            "input": {
                "prompt": enhanced_prompt,
                "aspect_ratio": "1:1",
                "output_format": "webp"
            },
            "bothub": {
                "include_usage": True,
                "return_base64": False
            }
        }
        
        logger.info("🔄 Отправляю запрос на генерацию...")
        response = requests.post(url, headers=headers, json=data, timeout=120)
        logger.info(f"📡 Ответ генерации: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            image_url = result.get('url')
            if isinstance(image_url, list):
                image_url = image_url[0]
            
            if image_url:
                img_response = requests.get(image_url, timeout=30)
                if img_response.status_code == 200:
                    image_data = img_response.content
                    
                    if len(image_data) > 1000:
                        await status_msg.edit_text("🎨 Генерирую картинку... 100% ✅")
                        await asyncio.sleep(0.2)
                        
                        image_file = BufferedInputFile(file=image_data, filename="image.webp")
                        
                        if trial_remaining > 0:
                            use_trial_image(user_id)
                        else:
                            add_image_request(user_id)
                        
                        await message.answer_photo(
                            photo=image_file,
                            caption=f"🖼️ **Твоя картинка**\n📝 {user_prompt[:100]}{'...' if len(user_prompt) > 100 else ''}"
                        )
                        
                        await status_msg.delete()
                        logger.info("✅ Картинка отправлена!")
                        return
        
        await status_msg.edit_text("❌ Не удалось получить картинку. Попробуй другой запрос.")
            
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

# ВСЕ CALLBACK'и
@router.callback_query(F.data.in_(["mode_text", "mode_image"]))
async def set_mode(callback: types.CallbackQuery):
    mode = callback.data.replace("mode_", "")
    user_modes[callback.from_user.id] = mode
    await callback.answer(f"✅ Режим: {'🧠 Текст' if mode == 'text' else '🖼️ Картинка'}", show_alert=True)
    await callback.message.edit_text(
        f"{'🧠 **Режим Текст**' if mode == 'text' else '🖼️ **Режим Картинка**'}\n\n"
        f"Теперь я {'отвечаю текстом' if mode == 'text' else 'генерирую картинки'} по твоим запросам!",
        reply_markup=main_menu()
    )

@router.callback_query(F.data == "stats")
async def stats_cb(callback: types.CallbackQuery):
    await stats_cmd(callback.message)
    await callback.answer()

@router.callback_query(F.data == "profile")
async def profile_cb(callback: types.CallbackQuery):
    await profile_cmd(callback.message)
    await callback.answer()

@router.callback_query(F.data == "referral")
async def referral_cb(callback: types.CallbackQuery):
    await referral_cmd(callback.message)
    await callback.answer()

@router.callback_query(F.data == "premium")
async def premium_cb(callback: types.CallbackQuery):
    await subscribe_cmd(callback.message)
    await callback.answer()

@router.callback_query(F.data == "help")
async def help_cb(callback: types.CallbackQuery):
    await callback.message.edit_text("❓ **Помощь**\n\n/start — меню\n/profile — профиль\n/stats — статистика\n/subscribe — Premium\n/referral — рефералы\n\n💎 Premium: безлимит + 50 картинок/день", reply_markup=main_menu())
    await callback.answer()

@router.callback_query(F.data == "leaderboard")
async def leaderboard_cb(callback: types.CallbackQuery):
    cursor.execute("SELECT user_id, username, total_requests FROM users ORDER BY total_requests DESC LIMIT 10")
    users = cursor.fetchall()
    if not users: 
        return await callback.answer("Нет данных")
    text = "🏆 **Рейтинг**\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, u in enumerate(users):
        medal = medals[i] if i < 3 else f"{i+1}."
        text += f"{medal} `{u[0]}` — {u[1] or 'без имени'} — {u[2]} задач\n"
    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()

@router.callback_query(F.data == "contact_admin")
async def contact_cb(callback: types.CallbackQuery):
    user_pages[callback.from_user.id] = {"state": "waiting_contact"}
    await callback.message.edit_text("📩 Напишите сообщение админу.\n⏹ /cancel", reply_markup=main_menu())
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def back_main_cb(callback: types.CallbackQuery):
    await callback.message.edit_text("🤖 **Vertex AI**\n\nПросто напиши вопрос!", reply_markup=main_menu())
    await callback.answer()

@router.callback_query(F.data.startswith("pay_"))
async def pay_cb(callback: types.CallbackQuery):
    plan = callback.data.replace("pay_", "")
    days = {"1": 30, "3": 90, "6": 180, "12": 365}[plan]
    stars = {"1": 49, "3": 129, "6": 249, "12": 449}[plan]
    payload = secrets.token_hex(16)
    cursor.execute("INSERT INTO payments (user_id, stars_amount, telegram_payload, status, timestamp) VALUES (?, ?, ?, ?, ?)",
                (callback.from_user.id, stars, payload, "pending", datetime.now().isoformat()))
    conn.commit()
    await callback.bot.send_invoice(callback.from_user.id, f"Premium {plan} мес", f"{days} дней", payload, "", "XTR", [LabeledPrice(label="Premium", amount=stars)], start_parameter="premium_sub")
    await callback.answer()

@router.pre_checkout_query()
async def pre_checkout(query: types.PreCheckoutQuery):
    await query.answer(ok=True)

@router.message(F.successful_payment)
async def payment_success(message: types.Message):
    payload = message.successful_payment.invoice_payload
    cursor.execute("SELECT stars_amount FROM payments WHERE telegram_payload = ?", (payload,))
    row = cursor.fetchone()
    days = {49: 30, 129: 90, 249: 180, 449: 365}.get(row[0] if row else 49, 30)
    if row:
        cursor.execute("UPDATE payments SET status = 'completed' WHERE telegram_payload = ?", (payload,))
        conn.commit()
    add_premium(message.from_user.id, days)
    GitHubBackup().backup_db()
    await message.answer(f"✅ Premium на {days} дней активирован!")

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
    if not is_admin(callback.from_user.id): return await callback.answer("⛔ Нет доступа")
    total, prem, req = get_stats()
    await callback.message.edit_text(f"📊 **Статистика**\n\n👥 Всего: {total}\n💎 Premium: {prem}\n📝 Запросов: {req}", reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_users")
async def a_users_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return await callback.answer("⛔ Нет доступа")
    cursor.execute("SELECT user_id, username, total_requests FROM users ORDER BY user_id LIMIT 20")
    users = cursor.fetchall()
    if not users:
        text = "👥 Пользователей не найдено"
    else:
        text = "👥 **Пользователи**\n\n" + "\n".join([f"🆔 `{u[0]}` — {u[1] or 'без имени'} — {u[2]} запросов" for u in users])
    await callback.message.edit_text(text, reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_give_premium")
async def a_give_premium_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return await callback.answer("⛔ Нет доступа")
    user_pages[callback.from_user.id] = {"state": "waiting_premium_user"}
    await callback.message.edit_text("💎 Введи ID пользователя и дни (пример: 123456 30)", reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_broadcast")
async def a_broadcast_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return await callback.answer("⛔ Нет доступа")
    user_pages[callback.from_user.id] = {"state": "waiting_broadcast"}
    await callback.message.edit_text("📢 Введи текст рассылки", reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_backup")
async def a_backup_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return await callback.answer("⛔ Нет доступа")
    await callback.message.edit_text("⏳ Создаю бэкап...")
    result = GitHubBackup().backup_db()
    await callback.message.edit_text("✅ Бэкап создан!" if result else "❌ Ошибка", reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_limits")
async def a_limits_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return await callback.answer("⛔ Нет доступа")
    text = f"⚙️ **Лимиты**\n\n🔹 Бесплатно: {get_setting('free_input_chars')} симв, {get_setting('free_output_words')} слов\n🔸 Premium: {get_setting('premium_input_chars')} симв, {get_setting('premium_output_words')} слов\n🖼️ Картинки: {get_setting('image_limit_free')} (бесплатно), {get_setting('image_limit_premium')} (Premium)"
    await callback.message.edit_text(text, reply_markup=admin_kb())
    await callback.answer()

@router.message(F.text)
async def handle_admin_input(message: types.Message):
    if not is_admin(message.from_user.id): return
    state = user_pages.get(message.from_user.id, {})
    
    if state.get("state") == "waiting_premium_user":
        try:
            parts = message.text.split()
            user_id, days = int(parts[0]), int(parts[1])
            add_premium(user_id, days)
            await message.answer(f"✅ Premium на {days} дней выдан пользователю {user_id}", reply_markup=admin_kb())
        except:
            await message.answer("❌ Формат: ID дни", reply_markup=admin_kb())
        user_pages.pop(message.from_user.id, None)
    
    elif state.get("state") == "waiting_broadcast":
        if message.text == "/cancel":
            user_pages.pop(message.from_user.id, None)
            return await message.answer("✅ Отменено", reply_markup=admin_kb())
        
        await message.answer("📢 Начинаю рассылку...")
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        sent = 0
        for u in users:
            try:
                await message.bot.send_message(u[0], f"📢 {message.text}")
                sent += 1
                await asyncio.sleep(0.05)
            except: pass
        await message.answer(f"✅ Рассылка завершена. Отправлено: {sent}", reply_markup=admin_kb())
        user_pages.pop(message.from_user.id, None)
    
    elif state.get("state") == "waiting_contact":
        user_id = message.from_user.id
        cursor.execute("INSERT INTO messages_to_admin (user_id, username, text, date) VALUES (?, ?, ?, ?)",
                    (user_id, message.from_user.username or "", message.text, datetime.now().isoformat()))
        conn.commit()
        await message.bot.send_message(int(os.getenv('ADMIN_ID', 6957852385)), f"📩 От {user_id}:\n{message.text}")
        await message.answer("✅ Отправлено админу!", reply_markup=main_menu())
        user_pages.pop(user_id, None)
