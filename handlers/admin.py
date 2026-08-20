from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from database.db import *
from . import helpers
from backup import GitHubBackup
import logging, os, sqlite3, asyncio, time

router = Router()
logger = logging.getLogger(__name__)

ADMIN_CODE = "30121979"

@router.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if is_admin(message.from_user.id):
        await message.answer("🛡️ **АДМИН-ПАНЕЛЬ**", reply_markup=helpers.admin_kb())
    else:
        await message.answer("🔐 Введите код: /admin_code 30121979")

@router.message(Command("admin_code"))
async def admin_code_cmd(message: types.Message):
    args = message.text.split() if message.text else []
    if len(args) > 1 and args[1] == ADMIN_CODE:
        add_admin(message.from_user.id)
        await message.answer("✅ Вы админ!", reply_markup=helpers.admin_kb())

@router.callback_query(F.data == "admin_panel")
async def admin_panel_cb(callback: types.CallbackQuery):
    if is_admin(callback.from_user.id):
        await safe_edit(callback, "🛡️ **АДМИН-ПАНЕЛЬ**", helpers.admin_kb())
    else:
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)

async def safe_edit(callback, text, reply_markup=None):
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except Exception as e:
        if "there is no text in the message to edit" in str(e) or "message is not modified" in str(e):
            await callback.message.answer(text, reply_markup=reply_markup)
        else:
            raise

def get_users_from_db():
    def _get_users(conn, cursor):
        cursor.execute("SELECT user_id, username, tokens, is_blocked FROM users WHERE user_id != 8676871187 ORDER BY tokens DESC LIMIT 50")
        return cursor.fetchall()
    return _execute_db(_get_users)

def get_messages_from_db():
    def _get_messages(conn, cursor):
        cursor.execute("SELECT id, user_id, username, text, date FROM messages_to_admin ORDER BY date DESC LIMIT 20")
        return cursor.fetchall()
    return _execute_db(_get_messages)

def get_promocodes_from_db():
    def _get_promocodes(conn, cursor):
        cursor.execute("SELECT * FROM promocodes ORDER BY created_at DESC")
        return cursor.fetchall()
    return _execute_db(_get_promocodes)

# ===== НАГРУЗОЧНЫЙ ТЕСТ (1000 ПОЛЬЗОВАТЕЛЕЙ) =====
@router.callback_query(F.data == "a_load_test")
async def load_test_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    
    await safe_edit(callback, "⏳ **Запуск теста нагрузки (1000 пользователей)...**\n\nОчередь будет заполняться!", helpers.admin_kb())
    
    asyncio.create_task(run_load_test(callback))

async def run_load_test(callback):
    """Запускает нагрузочный тест и обновляет статус"""
    user_id = callback.from_user.id
    
    try:
        total_users = 1000  # ← 1000 ПОЛЬЗОВАТЕЛЕЙ!
        
        for i in range(total_users):
            test_user_id = 9000000 + i
            create_user(test_user_id, f"load_{i}")
            add_tokens(test_user_id, 10)
            
            # Обновляем статус каждые 100 пользователей
            if i % 100 == 0:
                status = get_queue_info()
                await callback.message.edit_text(
                    f"🔄 **Нагрузочный тест**\n\n"
                    f"📊 Прогресс: {i+1}/{total_users}\n"
                    f"{status}\n\n"
                    f"⏳ Продолжаем...",
                    reply_markup=helpers.admin_kb()
                )
                await asyncio.sleep(0.1)
        
        status = get_queue_info()
        await callback.message.edit_text(
            f"✅ **Тест завершён!**\n\n"
            f"👥 Создано {total_users} пользователей\n"
            f"🪙 Каждому добавлено 10 токенов\n\n"
            f"{status}",
            reply_markup=helpers.admin_kb()
        )
        
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка: {e}",
            reply_markup=helpers.admin_kb()
        )

# ===== ВСЕ АДМИН-ФУНКЦИИ =====

@router.callback_query(F.data == "a_stats")
async def a_stats_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    total, total_tokens, total_requests, total_images, premium_users = get_stats()
    text = (
        f"📊 **СТАТИСТИКА**\n\n"
        f"👥 Всего: {total}\n"
        f"💎 Премиум: {premium_users}\n"
        f"💰 Токенов: {total_tokens}\n"
        f"📝 Запросов: {total_requests}\n"
        f"🖼️ Картинок: {total_images}"
    )
    await safe_edit(callback, text, helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_model_stats")
async def a_model_stats_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    total = sum(helpers.model_stats.values())
    if total > 0:
        text = "📈 **МОДЕЛИ**\n\nВсего: " + str(total) + "\n\n"
        for key, count in helpers.model_stats.items():
            if count > 0:
                model = helpers.IMAGE_MODELS[key]
                text += f"{model['name']}: {count} ({round(count/total*100,1)}%)\n"
    else:
        text = "📈 **МОДЕЛИ**\n\n❌ Нет статистики."
    await safe_edit(callback, text, helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_users")
async def a_users_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    
    try:
        users = get_users_from_db()
        
        if not users:
            text = "👥 Нет пользователей"
        else:
            text = "👥 **Топ**\n\n"
            for u in users:
                status = "⛔" if u['is_blocked'] == 1 else "✅"
                name = u['username'] if u['username'] and u['username'] != str(u['user_id']) else "Без имени"
                text += f"{status} {name}: {u['tokens']} токенов\n"
    except Exception as e:
        logger.error(f"Ошибка получения пользователей: {e}")
        text = "❌ Ошибка загрузки пользователей"
    
    await safe_edit(callback, text[:4000], helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_give_tokens")
async def a_give_tokens_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_give_tokens"}
    await safe_edit(callback, "⭐ **Раздать токены**\n\nФормат: `ID | кол-во` или `всем | кол-во`", helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_broadcast")
async def a_broadcast_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_broadcast"}
    await safe_edit(callback, "📢 **Рассылка**\n\nВведите текст.", helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_block")
async def a_block_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    
    try:
        users = get_users_from_db()
        
        if not users:
            await safe_edit(callback, "👥 Нет пользователей", helpers.admin_kb())
            await helpers.safe_answer(callback)
            return
        
        kb = InlineKeyboardMarkup(inline_keyboard=[])
        for u in users:
            name = u['username'] if u['username'] and u['username'] != str(u['user_id']) else str(u['user_id'])
            status = "✅" if u['is_blocked'] == 0 else "⛔"
            kb.inline_keyboard.append([InlineKeyboardButton(text=f"{status} {name}", callback_data=f"block_user_{u['user_id']}")])
        kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])
        await safe_edit(callback, "🚫 **Блокировка**\n\nНажмите на пользователя:", kb)
    except Exception as e:
        logger.error(f"Ошибка загрузки блокировки: {e}")
        await safe_edit(callback, "❌ Ошибка загрузки", helpers.admin_kb())
    
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("block_user_"))
async def block_user_action(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    user_id = int(callback.data.replace("block_user_", ""))
    user = get_user(user_id)
    if not user:
        await helpers.safe_answer(callback, "❌ Не найден", show_alert=True)
        return
    if user['is_blocked'] == 1:
        unblock_user(user_id)
        await helpers.safe_answer(callback, "✅ Разблокирован", show_alert=True)
    else:
        block_user(user_id)
        await helpers.safe_answer(callback, "⛔ Заблокирован", show_alert=True)
    do_backup()
    await a_block_cb(callback)

@router.callback_query(F.data == "a_messages")
async def a_messages_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    
    try:
        msgs = get_messages_from_db()
        
        if not msgs:
            await safe_edit(callback, "📭 Нет обращений.", helpers.admin_kb())
            await helpers.safe_answer(callback)
            return
        
        text = "📩 **Обращения**\n\n"
        for m in msgs:
            name = m['username'] if m['username'] and m['username'] != str(m['user_id']) else str(m['user_id'])
            text += f"👤 {name}: {m['text'][:50]}\n🕐 {m['date'][:16]}\n\n"
        await safe_edit(callback, text[:4000], helpers.admin_kb())
    except Exception as e:
        logger.error(f"Ошибка загрузки сообщений: {e}")
        await safe_edit(callback, "❌ Ошибка загрузки", helpers.admin_kb())
    
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_backup")
async def a_backup_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    await safe_edit(callback, "⏳ Бэкап...", None)
    result = GitHubBackup().backup_db()
    await safe_edit(callback, "✅ Бэкап создан!" if result else "❌ Ошибка", helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_export_db")
async def export_db_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    if not os.path.exists('data/repsolver.db'):
        await safe_edit(callback, "❌ БД не найдена", helpers.admin_kb())
        await helpers.safe_answer(callback)
        return
    try:
        await callback.message.delete()
        await callback.message.answer_document(
            BufferedInputFile(open('data/repsolver.db', 'rb').read(), filename="repsolver.db"),
            caption="📁 База данных", reply_markup=helpers.admin_kb()
        )
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}", reply_markup=helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_restore_github")
async def restore_github_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    result = GitHubBackup().restore_latest_backup()
    await safe_edit(callback, "✅ БД восстановлена!" if result else "❌ Ошибка", helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_edit_prices")
async def a_edit_prices_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for key, model in helpers.IMAGE_MODELS.items():
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{model['name']} — {model['price']} токенов", callback_data=f"edit_price_{key}")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])
    await safe_edit(callback, "💰 **Цены**\n\nВыбери модель:", kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data.startswith("edit_price_"))
async def edit_price_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    model_key = callback.data.replace("edit_price_", "")
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_price", "model": model_key}
    await safe_edit(callback, f"💰 Введи новую цену для {helpers.IMAGE_MODELS[model_key]['name']}:", helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_promocodes")
async def a_promocodes_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать", callback_data="a_create_promo")],
        [InlineKeyboardButton(text="📋 Список", callback_data="a_list_promos")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ])
    await safe_edit(callback, "🎫 **Промокоды**", kb)
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_create_promo")
async def a_create_promo_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    helpers.user_pages[callback.from_user.id] = {"state": "waiting_promo_code"}
    await safe_edit(callback, "🎫 **Создание**\n\nФормат: `код | токены | дни`\n\nПример: `WELCOME | 100 | 30`", helpers.admin_kb())
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_list_promos")
async def a_list_promos_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    
    try:
        promos = get_promocodes_from_db()
        
        if not promos:
            await safe_edit(callback, "📋 Нет промокодов", helpers.admin_kb())
            await helpers.safe_answer(callback)
            return
        
        text = "📋 **Промокоды**\n\n"
        for p in promos:
            text += f"🔹 `{p['code']}` +{p['bonus_tokens']} токенов, {p['used']}/{p['max_uses']}, до {p['expires_at'][:10]}\n"
        await safe_edit(callback, text[:4000], helpers.admin_kb())
    except Exception as e:
        logger.error(f"Ошибка загрузки промокодов: {e}")
        await safe_edit(callback, "❌ Ошибка загрузки", helpers.admin_kb())
    
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_db_status")
async def a_db_status_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    
    try:
        text = get_queue_info()
        await safe_edit(callback, text, helpers.admin_kb())
    except Exception as e:
        await safe_edit(callback, f"❌ Ошибка: {e}", helpers.admin_kb())
    
    await helpers.safe_answer(callback)

@router.callback_query(F.data == "a_stars_balance")
async def a_stars_balance_cb(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await helpers.safe_answer(callback, "⛔ Нет доступа", show_alert=True)
        return
    try:
        balance = await callback.bot.get_my_star_balance()
        byn = balance * 0.013
        rub = balance * 0.45
        text = (
            f"⭐ **Баланс Stars**\n\n"
            f"На счету: {balance} Stars\n"
            f"💵 ≈ {byn:.2f} BYN ≈ {rub:.2f} ₽\n"
            f"💡 Мин. вывод: 1000 Stars"
        )
        await safe_edit(callback, text, helpers.admin_kb())
    except Exception as e:
        await safe_edit(callback, f"❌ Ошибка: {e}", helpers.admin_kb())
    await helpers.safe_answer(callback)

# ===== АДМИН-ВВОД =====
async def handle_admin_input(message: types.Message):
    """Обрабатывает ввод от админа (рассылка, промокоды, раздача токенов)"""
    user_id = message.from_user.id
    state = helpers.user_pages.get(user_id, {})
    
    if message.text == "/cancel":
        helpers.user_pages.pop(user_id, None)
        await message.answer("✅ Отменено", reply_markup=helpers.admin_kb())
        return
    
    # === СОЗДАНИЕ ПРОМОКОДА ===
    if state.get("state") == "waiting_promo_code":
        try:
            parts = message.text.strip().split("|")
            if len(parts) < 2:
                await message.answer("❌ Формат: код | токены | дни")
                return
            code = parts[0].strip().upper()
            bonus = int(parts[1].strip())
            days = int(parts[2].strip()) if len(parts) > 2 else 30
            conn = sqlite3.connect('data/repsolver.db')
            cursor = conn.cursor()
            expires = (datetime.now() + timedelta(days=days)).isoformat()
            cursor.execute("INSERT INTO promocodes (code, bonus_tokens, max_uses, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                          (code, bonus, 100, datetime.now().isoformat(), expires))
            conn.commit()
            conn.close()
            await message.answer(f"✅ Промокод `{code}` создан! +{bonus} токенов, {days} дней", reply_markup=helpers.admin_kb())
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}", reply_markup=helpers.admin_kb())
        helpers.user_pages.pop(user_id, None)
        return
    
    # === ИЗМЕНЕНИЕ ЦЕН ===
    if state.get("state") == "waiting_price":
        try:
            new_price = int(message.text.strip())
            if new_price < 1:
                await message.answer("❌ Цена > 0", reply_markup=helpers.admin_kb())
                return
            model_key = state.get("model")
            if model_key and model_key in helpers.IMAGE_MODELS:
                helpers.IMAGE_MODELS[model_key]["price"] = new_price
                await message.answer(f"✅ Цена обновлена: {new_price}", reply_markup=helpers.admin_kb())
        except:
            await message.answer("❌ Введи число", reply_markup=helpers.admin_kb())
        helpers.user_pages.pop(user_id, None)
        return
    
    # === РАЗДАЧА ТОКЕНОВ ===
    if state.get("state") == "waiting_give_tokens":
        try:
            text = message.text.strip()
            if text.startswith("всем") or text.startswith("all"):
                parts = text.split("|")
                amount = int(parts[1].strip()) if len(parts) > 1 else 10
                conn = sqlite3.connect('data/repsolver.db')
                cursor = conn.cursor()
                cursor.execute("SELECT user_id FROM users WHERE is_blocked = 0")
                users = cursor.fetchall()
                conn.close()
                count = 0
                for u in users:
                    add_tokens(u['user_id'], amount)
                    count += 1
                await message.answer(f"✅ Раздано {amount} токенов {count} пользователям", reply_markup=helpers.admin_kb())
            else:
                parts = text.split("|")
                if len(parts) < 2:
                    await message.answer("❌ Формат: ID | количество")
                    return
                target_id = int(parts[0].strip())
                amount = int(parts[1].strip())
                add_tokens(target_id, amount)
                await message.answer(f"✅ {target_id} +{amount} токенов", reply_markup=helpers.admin_kb())
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}", reply_markup=helpers.admin_kb())
        helpers.user_pages.pop(user_id, None)
        return
    
    # === РАССЫЛКА ===
    if state.get("state") == "waiting_broadcast":
        if not message.text or not message.text.strip():
            await message.answer("❌ Пустой текст", reply_markup=helpers.admin_kb())
            helpers.user_pages.pop(user_id, None)
            return
        
        await message.answer("📢 Рассылка...")
        conn = sqlite3.connect('data/repsolver.db')
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
        
        await message.answer(f"✅ Отправлено: {sent}", reply_markup=helpers.admin_kb())
        do_backup()
        helpers.user_pages.pop(user_id, None)
        return
    
    # === ОБРАЩЕНИЕ В ПОДДЕРЖКУ ===
    if state.get("state") == "waiting_contact":
        conn = sqlite3.connect('data/repsolver.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO messages_to_admin (user_id, username, text, date) VALUES (?, ?, ?, ?)",
                      (user_id, message.from_user.username or "", message.text, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        await message.bot.send_message(os.getenv('ADMIN_ID', 6957852385), f"📩 От {user_id}:\n{message.text}")
        await message.answer("✅ Отправлено!", reply_markup=helpers.main_menu())
        helpers.user_pages.pop(user_id, None)
        return
