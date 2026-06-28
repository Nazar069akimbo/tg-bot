from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
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

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🧠 Текст", "mode_text"), InlineKeyboardButton("🖼️ Картинка", "mode_image")],
        [InlineKeyboardButton("👤 Профиль", "profile"), InlineKeyboardButton("📊 Статистика", "stats")],
        [InlineKeyboardButton("👥 Рефералы", "referral"), InlineKeyboardButton("💎 Premium", "premium")],
        [InlineKeyboardButton("📩 Админу", "contact_admin"), InlineKeyboardButton("❓ Помощь", "help")],
        [InlineKeyboardButton("🏆 Рейтинг", "leaderboard"), InlineKeyboardButton("🛡️ Админ", "admin_panel")]
    ])

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("📊 Статистика", "a_stats"), InlineKeyboardButton("👥 Пользователи", "a_users")],
        [InlineKeyboardButton("📢 Рассылка", "a_broadcast"), InlineKeyboardButton("💎 Выдать Premium", "a_give_premium")],
        [InlineKeyboardButton("💾 Бэкап", "a_backup"), InlineKeyboardButton("⚙️ Лимиты", "a_limits")],
        [InlineKeyboardButton("🔙 Назад", "back_to_main")]
    ])

@router.message(Command("start"))
async def start_cmd(message: types.Message):
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
    user = get_user(message.from_user.id)
    if not user: return await message.answer("❌ /start")
    ok, rem = can_request(message.from_user.id)
    used, limit, prem = get_image_stats(message.from_user.id)
    text = f"📊 **Статистика**\n\n📝 Запросов: {rem if not prem else '∞'}\n🖼️ Картинок: {used}/{limit}\n💎 {'Premium' if prem else 'Бесплатный'}\n🎁 Пробный: {get_trial_remaining(message.from_user.id)}"
    await message.answer(text)

@router.message(Command("profile"))
async def profile_cmd(message: types.Message):
    user = get_user(message.from_user.id)
    if not user: return await message.answer("❌ /start")
    cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (message.from_user.id,))
    refs = cursor.fetchone()[0] or 0
    used, limit, prem = get_image_stats(message.from_user.id)
    await message.answer(f"👤 **Профиль**\n\n🆔 {user[0]}\n📆 {user[2][:10] if user[2] else 'Нет'}\n📊 Запросов: {user[5] or 0}\n👥 Приглашено: {refs}\n💎 {'✅ Premium' if prem else '❌ Нет'}\n🖼️ Картинки: {used}/{limit}")

@router.message(Command("subscribe"))
async def subscribe_cmd(message: types.Message):
    await message.answer("💎 **Premium**\n\n1 мес — 49⭐\n3 мес — 129⭐\n6 мес — 249⭐\n12 мес — 449⭐", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("⭐ 1 мес 49⭐", "pay_1"), InlineKeyboardButton("⭐ 3 мес 129⭐", "pay_3")],
        [InlineKeyboardButton("⭐ 6 мес 249⭐", "pay_6"), InlineKeyboardButton("⭐ 12 мес 449⭐", "pay_12")],
        [InlineKeyboardButton("🔙 Назад", "back_to_main")]
    ]))

@router.message(Command("referral"))
async def referral_cmd(message: types.Message):
    user_id = message.from_user.id
    if not get_user(user_id): return await message.answer("❌ /start")
    cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
    count = cursor.fetchone()[0] or 0
    link = f"https://t.me/Vertex1bot?start={user_id}"
    await message.answer(f"👥 **Рефералы**\n\nПриглашено: {count}\nБонус: +5 запросов\n\n🔗 {link}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("📤 Поделиться", url=f"https://t.me/share/url?url={link}&text=🤖 Присоединяйся!")],
        [InlineKeyboardButton("🔙 Назад", "back_to_main")]
    ]))

@router.message(F.text)
async def handle_message(message: types.Message):
    if message.text.startswith("/"): return
    if not get_user(message.from_user.id): return await message.answer("👋 /start")
    
    mode = user_modes.get(message.from_user.id, "text")
    if mode == "image":
        await generate_image(message)
    else:
        await generate_text(message)

async def generate_text(message: types.Message):
    ok, rem = can_request(message.from_user.id)
    if not ok: return await message.answer("🔒 Лимит исчерпан! /subscribe")
    
    prem = is_premium(message.from_user.id)
    status = await message.answer("🤔 Думаю...")
    try:
        answer = solve_problem(message.text, "chat", prem)
        add_request(message.from_user.id)
        await status.edit_text(f"🧠 {answer}\n\n{'∞' if prem else rem-1} запросов осталось")
    except Exception as e:
        await status.edit_text(f"❌ Ошибка: {e}")

async def generate_image(message: types.Message):
    user_id = message.from_user.id
    can_gen, remaining = can_generate_image(user_id)
    used, limit, prem = get_image_stats(user_id)
    
    trial_rem = get_trial_remaining(user_id)
    if trial_rem > 0 and not prem:
        can_gen = True
        remaining = trial_rem
        limit = 5
    
    if not can_gen:
        return await message.answer(f"❌ Лимит картинок! {used}/{limit}\n💎 /subscribe")
    
    status = await message.answer("🎨 Генерирую...")
    try:
        prompt_resp = requests.post("https://openai.bothub.chat/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}", "Content-Type": "application/json"},
            json={"model": "gpt-4.1-nano", "messages": [{"role": "system", "content": "Create detailed English prompt for Flux/Stable Diffusion. 30-60 words. Only prompt!"}, {"role": "user", "content": f"Prompt for: {message.text}"}], "max_tokens": 200}
        )
        enhanced = prompt_resp.json().get('choices', [{}])[0].get('message', {}).get('content', message.text).strip('"')
        
        img_resp = requests.post("https://bothub.chat/api/v2/replicate/v1/images/generations",
            headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}", "Content-Type": "application/json"},
            json={"model": "flux-schnell", "input": {"prompt": enhanced, "aspect_ratio": "1:1", "output_format": "webp"}},
            timeout=60
        )
        img_url = img_resp.json().get('url')
        if isinstance(img_url, list): img_url = img_url[0]
        
        if img_url:
            img_data = requests.get(img_url).content
            if trial_rem > 0 and not prem:
                use_trial_image(user_id)
            else:
                add_image_request(user_id)
            
            from aiogram.types import BufferedInputFile
            await message.answer_photo(BufferedInputFile(img_data, "image.webp"), 
                caption=f"🖼️ {message.text[:50]}...\n📊 Осталось: {limit - used - 1}")
            await status.delete()
    except Exception as e:
        await status.edit_text(f"❌ Ошибка: {e}")

@router.callback_query(F.data.in_(["mode_text", "mode_image"]))
async def set_mode(callback: types.CallbackQuery):
    mode = callback.data.replace("mode_", "")
    user_modes[callback.from_user.id] = mode
    await callback.answer(f"✅ Режим: {'🧠 Текст' if mode == 'text' else '🖼️ Картинка'}", show_alert=True)

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
    if not users: return await callback.answer("Нет данных")
    text = "🏆 **Рейтинг**\n\n" + "\n".join([f"{'🥇🥈🥉'[i] if i<3 else f'{i+1}.'} `{u[0]}` — {u[1] or 'без имени'} — {u[2]} задач" for i, u in enumerate(users)])
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
    await callback.bot.send_invoice(callback.from_user.id, f"Premium {plan} мес", f"{days} дней", payload, "", "XTR", [LabeledPrice("Premium", stars)], start_parameter="premium_sub")
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
    await callback.message.edit_text(f"📊 **Статистика**\n\n👥 {total}\n💎 {prem}\n📝 {req}", reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "a_users")
async def a_users_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return await callback.answer("⛔ Нет доступа")
    cursor.execute("SELECT user_id, username, total_requests FROM users ORDER BY user_id LIMIT 20")
    users = cursor.fetchall()
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
