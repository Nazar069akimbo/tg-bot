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

def force_create_user(user_id, username=None):
    try:
        user = get_user(user_id)
        if user:
            if len(user) > 9 and user[9] == 'basic' and user[3] and user[3] > datetime.now().isoformat():
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

# ========== ГЛАВНОЕ МЕНЮ (как у конкурента) ==========

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧠 Текст", callback_data="mode_text"), InlineKeyboardButton(text="🖼️ Картинка", callback_data="mode_image")],
        [InlineKeyboardButton(text="🌐 Поиск", callback_data="search_mode"), InlineKeyboardButton(text="🎬 Видео", callback_data="video_mode")],
        [InlineKeyboardButton(text="👥 Рефералы", callback_data="referral"), InlineKeyboardButton(text="💎 Premium", callback_data="premium")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"), InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton(text="📩 Поддержка", callback_data="contact_admin"), InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ])

# ========== КОМАНДЫ (как у конкурента) ==========

@router.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    user = force_create_user(user_id, username)
    if not user:
        await message.answer("❌ Ошибка регистрации. Попробуйте позже.")
        return
    
    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        referrer_id = int(args[1])
        if referrer_id != user_id:
            success, msg = add_referral(referrer_id, user_id)
            if success:
                await message.answer(msg)
    
    text = (
        "🤖 **Vertex AI**\n\n"
        "🧠 Искусственный интеллект в Telegram!\n\n"
        "✅ **Бесплатно:** 10 запросов/день + 3 картинки\n"
        "💎 **Premium:** безлимит + 50 картинок/день (49⭐)\n"
        "👑 **Premium Deluxe:** безлимит + 200 картинок/день (99⭐)\n\n"
        "👥 Приведи друга → +3 картинки и +10 запросов\n\n"
        "📱 Просто напиши свой вопрос — ИИ ответит!\n\n"
        "📋 **Команды:**\n"
        "/profile — мой профиль\n"
        "/premium — Premium\n"
        "/referral — рефералы\n"
        "/help — помощь"
    )
    await message.answer(text, reply_markup=main_menu())

@router.message(Command("help"))
async def help_cmd(message: types.Message):
    text = (
        "❓ **Помощь по боту Vertex AI**\n\n"
        "📝 **Генерация текста**\n"
        "Просто напиши вопрос в чат\n\n"
        "🖼️ **Генерация картинок**\n"
        "Нажми 'Картинка' или напиши запрос в режиме картинки\n\n"
        "🌐 **Поиск в интернете**\n"
        "Нажми 'Поиск' и задай вопрос\n\n"
        "👥 **Реферальная система**\n"
        "/referral — получить ссылку\n"
        "Бонус: +3 картинки и +10 запросов за друга\n\n"
        "💎 **Premium**\n"
        "/premium — подключить\n"
        "Безлимит текста, 50-200 картинок/день\n\n"
        "📊 **Статистика**\n"
        "/profile — посмотреть использование\n\n"
        "📩 **Поддержка**\n"
        "Нажми 'Поддержка' или напиши @i_abramov_gpt"
    )
    await message.answer(text, reply_markup=main_menu())

@router.message(Command("profile"))
async def profile_cmd(message: types.Message):
    user_id = message.from_user.id
    user = force_create_user(user_id, message.from_user.username or "")
    if not user:
        await message.answer("❌ Ошибка! Попробуйте позже.", reply_markup=main_menu())
        return
    
    used, limit, prem, plan = get_image_stats(user_id)
    total_requests = user[5] if len(user) > 5 and user[5] else 0
    total_images = user[8] if len(user) > 8 and user[8] else 0
    refs = get_referral_count(user_id)
    bonus_images, bonus_requests = get_referral_bonuses(user_id)
    plan_name = get_plan_emoji(plan)
    
    text = (
        f"👤 **Мой профиль**\n\n"
        f"🆔 ID: `{user[0]}`\n"
        f"💎 План: {plan_name}\n"
        f"📝 Запросов: {total_requests}\n"
        f"🖼️ Картинок: {total_images}\n"
        f"🖼️ Сегодня: {used}/{limit}\n"
        f"👥 Приглашено: {refs}\n"
        f"🎁 Бонусы: {bonus_images} карт, {bonus_requests} запросов\n"
        f"📆 Регистрация: {user[2][:10] if user[2] else 'Нет'}"
    )
    await message.answer(text, reply_markup=main_menu())

@router.message(Command("account"))
async def account_cmd(message: types.Message):
    await profile_cmd(message)

@router.message(Command("premium"))
async def premium_cmd(message: types.Message):
    user_id = message.from_user.id
    force_create_user(user_id, message.from_user.username or "")
    
    text = (
        "💎 **Premium подписка**\n\n"
        "🔴 **Бесплатный** — 0⭐\n"
        "• 10 текстовых запросов/день\n"
        "• 3 картинки/день\n\n"
        "💎 **Premium** — 49⭐/мес\n"
        "• Безлимит текстовых запросов\n"
        "• 50 картинок/день\n"
        "• Приоритетная обработка\n\n"
        "👑 **Premium Deluxe** — 99⭐/мес\n"
        "• Безлимит текстовых запросов\n"
        "• 200 картинок/день\n"
        "• Эксклюзивные промпты\n"
        "• VIP-поддержка 24/7"
    )
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Premium 49⭐", callback_data="pay_premium"), InlineKeyboardButton(text="👑 Deluxe 99⭐", callback_data="pay_deluxe")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
    )

@router.message(Command("subscribe"))
async def subscribe_cmd(message: types.Message):
    await premium_cmd(message)

@router.message(Command("referral"))
async def referral_cmd(message: types.Message):
    user_id = message.from_user.id
    user = force_create_user(user_id, message.from_user.username or "")
    if not user:
        await message.answer("❌ Ошибка! Попробуйте позже.", reply_markup=main_menu())
        return
    
    count = get_referral_count(user_id)
    bonus_images, bonus_requests = get_referral_bonuses(user_id)
    link = f"https://t.me/Vertex1bot?start={user_id}"
    
    text = (
        f"👥 **Реферальная система**\n\n"
        f"👤 Приглашено: {count}\n"
        f"🎁 Бонусы:\n"
        f"   🖼️ +{bonus_images} картинок\n"
        f"   📝 +{bonus_requests} запросов\n\n"
        f"🔗 Твоя ссылка:\n`{link}`\n\n"
        f"📤 Отправь ссылку друзьям!"
    )
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться", url=f"https://t.me/share/url?url={link}&text=🤖 Присоединяйся к Vertex AI!")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
    )

@router.message(Command("settings"))
async def settings_cmd(message: types.Message):
    user_id = message.from_user.id
    user = force_create_user(user_id, message.from_user.username or "")
    if not user:
        await message.answer("❌ Ошибка! Попробуйте позже.", reply_markup=main_menu())
        return
    
    mode = user_modes.get(user_id, "text")
    mode_text = "🧠 Текст" if mode == "text" else "🖼️ Картинка"
    
    text = (
        f"⚙️ **Настройки**\n\n"
        f"📊 Текущий режим: {mode_text}\n"
        f"💎 План: {get_plan_emoji(get_user_plan(user_id))}\n\n"
        f"📋 Доступные настройки:\n"
        f"• Режим работы: Текст / Картинка\n"
        f"• Язык: Русский\n"
        f"• Контекст: Включён\n\n"
        f"Изменить режим можно в главном меню."
    )
    await message.answer(text, reply_markup=main_menu())

@router.message(Command("deletecontext"))
async def delete_context_cmd(message: types.Message):
    user_id = message.from_user.id
    user_pages.pop(user_id, None)
    await message.answer(
        "🗑️ Контекст удалён.\n"
        "Теперь бот не будет учитывать предыдущие сообщения.",
        reply_markup=main_menu()
    )

@router.message(Command("s"))
async def search_cmd(message: types.Message):
    user_id = message.from_user.id
    user = force_create_user(user_id, message.from_user.username or "")
    if not user:
        await message.answer("❌ Ошибка! Попробуйте позже.", reply_markup=main_menu())
        return
    
    user_modes[user_id] = "search"
    await message.answer(
        "🌐 **Режим поиска**\n\n"
        "Напиши свой вопрос, и я найду ответ в интернете.\n\n"
        "⏹ Чтобы выйти из режима поиска, нажми /deletecontext",
        reply_markup=main_menu()
    )

@router.message(Command("photo"))
async def photo_cmd(message: types.Message):
    user_id = message.from_user.id
    user = force_create_user(user_id, message.from_user.username or "")
    if not user:
        await message.answer("❌ Ошибка! Попробуйте позже.", reply_markup=main_menu())
        return
    
    user_modes[user_id] = "image"
    await message.answer(
        "🖼️ **Режим генерации картинок**\n\n"
        "Напиши описание того, что хочешь создать.\n\n"
        "💡 Пример: 'Космический корабль на фоне галактики'\n\n"
        "⏹ Чтобы выйти, нажми /deletecontext",
        reply_markup=main_menu()
    )

@router.message(Command("video"))
async def video_cmd(message: types.Message):
    await message.answer(
        "🎬 **Генерация видео**\n\n"
        "🚧 Функция в разработке!\n\n"
        "Скоро здесь появится возможность создавать видео.\n"
        "Следите за обновлениями!",
        reply_markup=main_menu()
    )

@router.message(Command("music"))
async def music_cmd(message: types.Message):
    await message.answer(
        "🎸 **Генерация музыки**\n\n"
        "🚧 Функция в разработке!\n\n"
        "Скоро здесь появится возможность создавать песни.\n"
        "Следите за обновлениями!",
        reply_markup=main_menu()
    )

@router.message(Command("slides"))
async def slides_cmd(message: types.Message):
    await message.answer(
        "📊 **Презентации**\n\n"
        "🚧 Функция в разработке!\n\n"
        "Скоро здесь появится возможность создавать презентации.\n"
        "Следите за обновлениями!",
        reply_markup=main_menu()
    )

@router.message(Command("model"))
async def model_cmd(message: types.Message):
    await message.answer(
        "🧠 **Выбор модели**\n\n"
        "Текущая модель: **GPT-4o mini**\n\n"
        "Доступные модели:\n"
        "• GPT-4o mini (бесплатно)\n"
        "• DeepSeek V4 (бесплатно)\n"
        "• Gemini 3.1 Flash (бесплатно)\n"
        "• GPT-5.5 (Premium)\n"
        "• Claude 4.8 Opus (Premium)\n"
        "• Gemini 3.5 Flash (Premium)\n\n"
        "💎 Чтобы получить доступ ко всем моделям, купи Premium — /premium",
        reply_markup=main_menu()
    )

@router.message(Command("privacy"))
async def privacy_cmd(message: types.Message):
    text = (
        "📋 **Пользовательское соглашение**\n\n"
        "1. Бот предоставляет услуги генерации текста и изображений\n"
        "2. Пользователь несёт ответственность за использование контента\n"
        "3. Бот не хранит личные данные пользователей\n"
        "4. Premium подписка не подлежит возврату\n"
        "5. Запрещено использовать бота для генерации запрещённого контента\n\n"
        "📩 По всем вопросам: @i_abramov_gpt"
    )
    await message.answer(text, reply_markup=main_menu())

# ========== ОБРАБОТКА ТЕКСТА ==========

@router.message(F.text)
async def handle_message(message: types.Message):
    if message.text.startswith("/"):
        return
    user_id = message.from_user.id
    state = user_pages.get(user_id, {})
    
    if state.get("state") in ["waiting_plan_edit", "waiting_premium_user", "waiting_broadcast", "waiting_block_user", "waiting_contact", "waiting_reply"]:
        await handle_admin_input(message)
        return
    
    user = force_create_user(user_id, message.from_user.username or "")
    if not user:
        await message.answer("❌ Ошибка! Попробуйте позже.", reply_markup=main_menu())
        return
    
    mode = user_modes.get(user_id, "text")
    
    if mode == "image":
        await generate_image(message)
    elif mode == "search":
        await generate_search(message)
    else:
        await generate_text(message)

async def generate_text(message: types.Message):
    user_id = message.from_user.id
    ok, rem = can_request(user_id)
    if not ok:
        return await message.answer("🔒 Лимит исчерпан! Купи Premium: /premium")
    prem = is_premium(user_id)
    status_msg = await message.answer("🤔 Думаю...")
    try:
        answer = solve_problem(message.text, "chat", prem)
        add_request(user_id)
        do_backup()
        await status_msg.edit_text(f"🧠 {answer}\n\n{'♾️ Безлимит' if prem else f'Осталось {rem-1} запросов'}")
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def generate_search(message: types.Message):
    user_id = message.from_user.id
    ok, rem = can_request(user_id)
    if not ok:
        return await message.answer("🔒 Лимит исчерпан! Купи Premium: /premium")
    
    status_msg = await message.answer("🌐 Ищу в интернете...")
    try:
        # Здесь можно добавить реальный поиск через API
        await status_msg.edit_text(
            f"🌐 **Результаты поиска:**\n\n"
            f"🔍 Запрос: {message.text[:100]}\n\n"
            f"📌 Функция поиска в разработке.\n"
            f"Скоро здесь будут результаты из интернета!"
        )
        add_request(user_id)
        do_backup()
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def generate_image(message: types.Message):
    user_id = message.from_user.id
    if not API_KEY:
        return await message.answer("❌ API ключ не настроен")
    
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
        return await message.answer(f"❌ Лимит картинок! {used}/{limit}\n💎 Купи Premium: /premium")
    
    status_msg = await message.answer("🎨 Генерирую картинку...")
    try:
        user_prompt = message.text
        prompt_resp = requests.post(
            "https://openai.bothub.chat/v1/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={"model": PROMPT_MODEL, "messages": [{"role": "system", "content": "Create detailed English prompt for Flux. Only the prompt!"}, {"role": "user", "content": f"Prompt for: {user_prompt}"}], "max_tokens": 200},
            timeout=30
        )
        enhanced = user_prompt
        if prompt_resp.status_code == 200:
            enhanced = prompt_resp.json().get('choices', [{}])[0].get('message', {}).get('content', user_prompt).strip('"')
        
        for p in [10, 25, 45, 60, 75, 90]:
            await asyncio.sleep(0.2)
            try:
                await status_msg.edit_text(f"🎨 {p}%")
            except:
                pass
        
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
                    
                    if trial_rem > 0:
                        use_trial_image(user_id)
                    else:
                        add_image_request(user_id)
                    
                    do_backup()
                    
                    new_used, new_limit, new_prem, new_plan = get_image_stats(user_id)
                    plan_emoji = get_plan_emoji(new_plan)
                    remaining = new_limit - new_used
                    
                    await message.answer_photo(
                        BufferedInputFile(file=img_data.content, filename="image.webp"),
                        caption=f"🖼️ **Твоя картинка**\n📝 {user_prompt[:50]}...\n\n📊 Осталось: {remaining}\n💎 План: {plan_emoji}"
                    )
                    await status_msg.delete()
                    return
        
        await status_msg.edit_text("❌ Не удалось получить картинку")
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

# ========== CALLBACK'и ==========

@router.callback_query(F.data == "mode_text")
async def mode_text_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_modes[user_id] = "text"
    await callback.answer("✅ Режим: Текст", show_alert=True)
    await callback.message.edit_text("🧠 **Режим Текст**\n\nТеперь я отвечаю текстом на твои вопросы.", reply_markup=main_menu())

@router.callback_query(F.data == "mode_image")
async def mode_image_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_modes[user_id] = "image"
    await callback.answer("✅ Режим: Картинка", show_alert=True)
    await callback.message.edit_text("🖼️ **Режим Картинка**\n\nТеперь я генерирую картинки по твоим описаниям.", reply_markup=main_menu())

@router.callback_query(F.data == "search_mode")
async def search_mode_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_modes[user_id] = "search"
    await callback.answer("✅ Режим: Поиск", show_alert=True)
    await callback.message.edit_text("🌐 **Режим Поиск**\n\nНапиши вопрос, и я найду ответ в интернете.", reply_markup=main_menu())

@router.callback_query(F.data == "video_mode")
async def video_mode_cb(callback: types.CallbackQuery):
    await callback.answer("🚧 В разработке", show_alert=True)
    await callback.message.edit_text("🎬 **Генерация видео**\n\n🚧 Функция в разработке!\nСкоро здесь появится создание видео.", reply_markup=main_menu())

@router.callback_query(F.data == "profile")
async def profile_cb(callback: types.CallbackQuery):
    await callback.answer()
    await profile_cmd(callback.message)

@router.callback_query(F.data == "settings")
async def settings_cb(callback: types.CallbackQuery):
    await callback.answer()
    await settings_cmd(callback.message)

@router.callback_query(F.data == "referral")
async def referral_cb(callback: types.CallbackQuery):
    await callback.answer()
    await referral_cmd(callback.message)

@router.callback_query(F.data == "premium")
async def premium_cb(callback: types.CallbackQuery):
    await callback.answer()
    await premium_cmd(callback.message)

@router.callback_query(F.data == "contact_admin")
async def contact_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    user_pages[user_id] = {"state": "waiting_contact"}
    await callback.message.edit_text("📩 Напишите сообщение админу.\n\n⏹ /cancel", reply_markup=main_menu())
    await callback.answer()

@router.callback_query(F.data == "help")
async def help_cb(callback: types.CallbackQuery):
    await callback.answer()
    await help_cmd(callback.message)

@router.callback_query(F.data == "back_to_main")
async def back_main_cb(callback: types.CallbackQuery):
    await callback.answer()
    await start_cmd(callback.message)

@router.callback_query(F.data.startswith("pay_"))
async def pay_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    force_create_user(user_id, callback.from_user.username or "")
    try:
        plan_type = callback.data.replace("pay_", "")
        if plan_type == "premium":
            stars, days, plan = 49, 30, "premium"
            title = "Premium 1 мес"
        elif plan_type == "deluxe":
            stars, days, plan = 99, 30, "premium_deluxe"
            title = "Premium Deluxe 1 мес"
        else:
            return await callback.answer("❌ Неверный тариф", show_alert=True)
        payload = secrets.token_hex(16)
        
        from database.db import get_db
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO payments (user_id, stars_amount, telegram_payload, status, timestamp, plan) VALUES (?, ?, ?, ?, ?, ?)",
                        (user_id, stars, payload, "pending", datetime.now().isoformat(), plan))
        
        await callback.bot.send_invoice(
            chat_id=user_id, title=title, description=f"{days} дней Premium",
            payload=payload, provider_token="", currency="XTR",
            prices=[LabeledPrice(label=title, amount=stars)], start_parameter="premium_sub"
        )
        await callback.answer()
    except Exception as e:
        await callback.answer("❌ Ошибка платежа", show_alert=True)

@router.pre_checkout_query()
async def pre_checkout(query: types.PreCheckoutQuery):
    await query.answer(ok=True)

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

# ========== АДМИНКА ==========

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

def admin_kb():
    new_messages = get_messages_count()
    badge = f" ({new_messages})" if new_messages > 0 else ""
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="a_stats"), InlineKeyboardButton(text="📈 График", callback_data="a_chart")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="a_users"), InlineKeyboardButton(text="💎 Выдать Premium", callback_data="a_give_premium")],
        [InlineKeyboardButton(text=f"📩 Обращения{badge}", callback_data="a_messages")],
        [InlineKeyboardButton(text="⚙️ Тарифы", callback_data="a_plans"), InlineKeyboardButton(text="🚫 Блокировка", callback_data="a_block")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="a_broadcast"), InlineKeyboardButton(text="💾 Бэкап", callback_data="a_backup")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

# ========== АДМИНКА: ВСЕ ОСТАЛЬНЫЕ ФУНКЦИИ ==========

@router.callback_query(F.data == "a_stats")
async def a_stats_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    total, prem, req, images, paid = get_stats()
    
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE plan = 'premium_deluxe' AND premium_until > datetime('now')")
        deluxe = cursor.fetchone()[0] or 0
    
    await callback.message.edit_text(
        f"📊 **СТАТИСТИКА БОТА**\n\n"
        f"👥 Всего пользователей: {total}\n"
        f"💎 Premium: {prem - deluxe}\n"
        f"👑 Premium Deluxe: {deluxe}\n"
        f"💰 Оплатили Premium: {paid}\n"
        f"📝 Всего запросов: {req}\n"
        f"🖼️ Всего картинок: {images}",
        reply_markup=admin_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "a_chart")
async def a_chart_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    data = get_daily_stats(30)
    
    if not data:
        await callback.message.edit_text(
            "📈 **График за месяц**\n\nНет данных для отображения.",
            reply_markup=admin_kb()
        )
        await callback.answer()
        return
    
    dates = [d['date'] for d in data]
    new_users = [d['new_users'] for d in data]
    payments = [d['payments'] for d in data]
    
    import matplotlib.pyplot as plt
    from io import BytesIO
    
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(dates, new_users, label='Новые пользователи', color='blue', marker='o', linewidth=2, markersize=4)
    ax.plot(dates, payments, label='Оплаты Premium', color='green', marker='s', linewidth=2, markersize=4)
    ax.set_xlabel('Дата')
    ax.set_ylabel('Количество')
    ax.set_title('📊 Статистика за 30 дней')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.tick_params(axis='x', rotation=45)
    ax.set_xticks([d for i, d in enumerate(dates) if i % 3 == 0])
    plt.tight_layout()
    
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150)
    buf.seek(0)
    plt.close()
    
    await callback.message.delete()
    await callback.message.answer_photo(
        BufferedInputFile(file=buf.getvalue(), filename="chart.png"),
        caption="📈 **График за 30 дней**\n\nСиний — новые пользователи\nЗелёный — оплаты Premium",
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
        cursor.execute("SELECT user_id, username, total_requests, image_requests, plan, is_blocked FROM users ORDER BY user_id LIMIT 20")
        users = cursor.fetchall()
    
    plan_emoji = {'basic': '🔴', 'premium': '💎', 'premium_deluxe': '👑'}
    if not users:
        text = "👥 Пользователей не найдено"
    else:
        text = "👥 **Пользователи**\n\n"
        for u in users:
            emoji = plan_emoji.get(u[4], '🔴')
            blocked = "🚫" if u[5] == 1 else "✅"
            text += f"{blocked} {emoji} `{u[0]}` — {u[1] or 'без имени'}\n"
            text += f"   📝{u[2]} запросов | 🖼️{u[3]} картинок\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "a_give_premium")
async def a_give_premium_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, plan FROM users WHERE plan = 'basic' ORDER BY user_id LIMIT 20")
        users = cursor.fetchall()
    
    if not users:
        await callback.message.edit_text("👥 Все пользователи уже имеют Premium!", reply_markup=admin_kb())
        await callback.answer()
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for u in users:
        username = u[1] or str(u[0])
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=f"👤 {username}", callback_data=f"give_premium_{u[0]}")
        ])
    
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])
    
    await callback.message.edit_text(
        "💎 **Выдать Premium**\n\nВыберите пользователя для выдачи Premium (30 дней):",
        reply_markup=kb
    )
    await callback.answer()

@router.callback_query(F.data.startswith("give_premium_"))
async def give_premium_confirm(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    user_id = int(callback.data.replace("give_premium_", ""))
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Premium (30 дней)", callback_data=f"confirm_premium_{user_id}_premium")],
        [InlineKeyboardButton(text="👑 Premium Deluxe (30 дней)", callback_data=f"confirm_premium_{user_id}_premium_deluxe")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="a_give_premium")]
    ])
    
    await callback.message.edit_text(
        f"👤 Пользователь: `{user_id}`\n\nВыберите план:",
        reply_markup=kb
    )
    await callback.answer()

@router.callback_query(F.data.startswith("confirm_premium_"))
async def confirm_premium(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    parts = callback.data.split("_")
    user_id = int(parts[2])
    plan = parts[3]
    
    add_premium(user_id, 30, plan)
    do_backup()
    
    plan_names = {'premium': '💎 Premium', 'premium_deluxe': '👑 Premium Deluxe'}
    
    await callback.message.edit_text(
        f"✅ {plan_names.get(plan, 'Premium')} на 30 дней выдан пользователю `{user_id}`!",
        reply_markup=admin_kb()
    )
    await callback.answer()

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
        await callback.message.edit_text(
            "📩 **Обращения**\n\nНет обращений.",
            reply_markup=admin_kb()
        )
        await callback.answer()
        return
    
    text = "📩 **Обращения**\n\n"
    for msg in messages:
        status = "🆕" if msg[5] == "new" else "✅"
        name = msg[2] or f"User_{msg[1]}"
        text += f"{status} `{msg[1]}` — {name}\n"
        text += f"📝 {msg[3][:50]}{'...' if len(msg[3]) > 50 else ''}\n"
        text += f"🕐 {msg[4][:16]}\n\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Ответить на последнее", callback_data="reply_last")],
        [InlineKeyboardButton(text="🗑️ Очистить все", callback_data="delete_all_messages")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text[:4000], reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "reply_last")
async def reply_last_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM messages_to_admin WHERE status = 'new' ORDER BY date DESC LIMIT 1")
        row = cursor.fetchone()
    
    if not row:
        await callback.answer("❌ Нет новых обращений", show_alert=True)
        return
    
    msg_id = row[0]
    user_pages[callback.from_user.id] = {"state": "waiting_reply", "msg_id": msg_id}
    
    await callback.message.edit_text(
        "✏️ Введите текст ответа.\n\n⏹ /cancel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="a_messages")]
        ])
    )
    await callback.answer()

@router.callback_query(F.data == "delete_all_messages")
async def delete_all_messages_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages_to_admin")
    
    await callback.answer("🗑️ Все обращения удалены", show_alert=True)
    await a_messages_cb(callback)

@router.callback_query(F.data == "a_block")
async def a_block_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    from database.db import get_db
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, is_blocked FROM users ORDER BY user_id LIMIT 20")
        users = cursor.fetchall()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for u in users:
        username = u[1] or str(u[0])
        status = "🔓" if u[2] == 0 else "🔒"
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=f"{status} {username}", callback_data=f"block_user_{u[0]}")
        ])
    
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])
    
    await callback.message.edit_text(
        "🚫 **Блокировка пользователей**\n\nНажмите на пользователя для блокировки/разблокировки:",
        reply_markup=kb
    )
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
    
    is_blocked = user[6] if len(user) > 6 else 0
    
    if is_blocked == 1:
        unblock_user(user_id)
        await callback.answer("✅ Пользователь РАЗБЛОКИРОВАН", show_alert=True)
    else:
        block_user(user_id)
        await callback.answer("🚫 Пользователь ЗАБЛОКИРОВАН", show_alert=True)
    
    do_backup()
    await a_block_cb(callback)

@router.callback_query(F.data == "a_plans")
async def a_plans_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    text = f"⚙️ **Тарифы**\n\n🔹 Бесплатный: {get_setting('image_limit_free')} карт, {get_setting('free_input_chars')} симв\n💎 Premium: {get_setting('image_limit_premium')} карт, {get_setting('premium_input_chars')} симв\n👑 Premium Deluxe: {get_setting('image_limit_premium_deluxe')} карт, {get_setting('premium_deluxe_input_chars')} симв"
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔹 Бесплатный", callback_data="edit_free"), InlineKeyboardButton(text="💎 Premium", callback_data="edit_premium")],
        [InlineKeyboardButton(text="👑 Premium Deluxe", callback_data="edit_deluxe")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ]))
    await callback.answer()

@router.callback_query(F.data.startswith("edit_"))
async def edit_plan_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    plan = callback.data.replace("edit_", "")
    plan_names = {'free': '🔹 Бесплатный', 'premium': '💎 Premium', 'deluxe': '👑 Premium Deluxe'}
    user_pages[callback.from_user.id] = {"state": "waiting_plan_edit", "plan": plan}
    await callback.message.edit_text(
        f"⚙️ **{plan_names.get(plan)}**\n\nВведите: `<картинки> <символы>`\nПример: `10 1000`\n\n⏹ /cancel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="a_plans")]])
    )
    await callback.answer()

@router.callback_query(F.data == "a_backup")
async def a_backup_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    await callback.message.edit_text("⏳ Бэкап...")
    result = GitHubBackup().backup_db()
    await callback.message.edit_text("✅ Бэкап создан!" if result else "❌ Ошибка", reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_broadcast")
async def a_broadcast_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    user_pages[callback.from_user.id] = {"state": "waiting_broadcast"}
    await callback.message.edit_text("📢 **Рассылка**\n\nВведите текст.\n\n⏹ /cancel", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]]))
    await callback.answer()

async def handle_admin_input(message: types.Message):
    user_id = message.from_user.id
    state = user_pages.get(user_id, {})
    
    if state.get("state") == "waiting_reply":
        if message.text == "/cancel":
            user_pages.pop(user_id, None)
            return await message.answer("✅ Отменено", reply_markup=admin_kb())
        
        msg_id = state.get("msg_id")
        reply_text = message.text
        
        from database.db import get_db
        with get_db() as conn:
            cursor = conn.cursor()
            msg = get_message_by_id(msg_id)
            if msg:
                user_id_target = msg[1]
                cursor.execute("UPDATE messages_to_admin SET status = 'answered' WHERE id = ?", (msg_id,))
                
                try:
                    await message.bot.send_message(
                        user_id_target,
                        f"📩 **Ответ от администратора:**\n\n{reply_text}"
                    )
                    
                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🗑️ Удалить это сообщение", callback_data=f"delete_msg_{msg_id}")],
                        [InlineKeyboardButton(text="🔙 Назад", callback_data="a_messages")]
                    ])
                    
                    await message.answer(
                        f"✅ Ответ отправлен пользователю `{user_id_target}`",
                        reply_markup=kb
                    )
                except Exception as e:
                    await message.answer(f"❌ Не удалось отправить: {e}", reply_markup=admin_kb())
            else:
                await message.answer("❌ Сообщение не найдено", reply_markup=admin_kb())
        
        user_pages.pop(user_id, None)
        return
    
    if state.get("state") == "waiting_plan_edit":
        if message.text == "/cancel":
            user_pages.pop(user_id, None)
            return await message.answer("✅ Отменено", reply_markup=admin_kb())
        try:
            parts = message.text.split()
            if len(parts) != 2:
                return await message.answer("❌ Формат: картинки символы", reply_markup=admin_kb())
            images, chars = int(parts[0]), int(parts[1])
            plan = state.get("plan")
            if plan == 'free':
                set_setting('image_limit_free', str(images))
                set_setting('free_input_chars', str(chars))
            elif plan == 'premium':
                set_setting('image_limit_premium', str(images))
                set_setting('premium_input_chars', str(chars))
            elif plan == 'deluxe':
                set_setting('image_limit_premium_deluxe', str(images))
                set_setting('premium_deluxe_input_chars', str(chars))
            await message.answer(f"✅ Обновлено: карт={images}, симв={chars}", reply_markup=admin_kb())
            do_backup()
            user_pages.pop(user_id, None)
        except:
            await message.answer("❌ Ошибка! Формат: картинки символы", reply_markup=admin_kb())
        return
    
    if state.get("state") == "waiting_broadcast":
        if message.text == "/cancel":
            user_pages.pop(user_id, None)
            return await message.answer("✅ Отменено", reply_markup=admin_kb())
        await message.answer("📢 Рассылка...")
        
        from database.db import get_db
        with get_db() as conn:
            cursor = conn.cursor()
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
        await message.answer("✅ Отправлено админу!", reply_markup=main_menu())
        user_pages.pop(user_id, None)
        return

@router.callback_query(F.data.startswith("delete_msg_"))
async def delete_message_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа")
    
    msg_id = int(callback.data.replace("delete_msg_", ""))
    delete_message(msg_id)
    await callback.answer("🗑️ Сообщение удалено", show_alert=True)
    await a_messages_cb(callback)

@router.message(Command("cancel"))
async def cancel_cmd(message: types.Message):
    user_pages.pop(message.from_user.id, None)
    await message.answer("✅ Отменено", reply_markup=main_menu())
