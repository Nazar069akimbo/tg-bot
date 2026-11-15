import os
import re

path = "bot.py"
if not os.path.exists(path):
    print("❌ Файл не найден")
    exit(1)

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Удаляем старый вебхук, если он есть
pattern = r"@app\.route\('/tribute_webhook'.*?(?=def run_flask|\n#|\Z)"
content = re.sub(pattern, "", content, flags=re.DOTALL)

# Добавляем новый вебхук перед run_flask
new_webhook = '''@app.route('/tribute_webhook', methods=['POST'])
def tribute_webhook():
    import hmac
    import hashlib
    from flask import request, jsonify
    
    # 1. Проверка подписи
    signature = request.headers.get('trbt-signature')
    api_key = os.getenv('TRIBUTE_API_KEY')
    
    if not signature or not api_key:
        logger.warning("⚠️ Вебхук без подписи или API-ключа")
        return jsonify({"error": "Unauthorized"}), 401
    
    expected = hmac.new(api_key.encode(), request.get_data(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        logger.warning("⚠️ Неверная подпись Tribute")
        return jsonify({"error": "Invalid signature"}), 401
    
    # 2. Парсим данные
    data = request.json
    event_name = data.get('name')
    
    if event_name != 'new_digital_product':
        return jsonify({"status": "ignored"}), 200
    
    payload = data.get('payload', {})
    tx_id = payload.get('transaction_id') or payload.get('id')
    user_id = payload.get('telegram_user_id')
    product_name = payload.get('product_name', '')
    
    if not user_id or not tx_id:
        logger.warning(f"⚠️ Вебхук без user_id или tx_id: {data}")
        return jsonify({"status": "no user or tx"}), 200
    
    # 3. Проверка на дубль
    if check_tribute_transaction(tx_id):
        logger.info(f"⏭ Транзакция {tx_id} уже была обработана")
        return jsonify({"status": "already processed"}), 200
        
    # 4. Определяем токены
    tokens_to_add = 0
    if "Старт" in product_name or "900" in product_name:
        tokens_to_add = 900
    elif "Базовый" in product_name or "1800" in product_name:
        tokens_to_add = 1800
    elif "Выгодный" in product_name or "2700" in product_name:
        tokens_to_add = 2700
    elif "Профи" in product_name or "3600" in product_name:
        tokens_to_add = 3600
    elif "Максимум" in product_name or "4500" in product_name:
        tokens_to_add = 4500
    else:
        logger.warning(f"⚠️ Неизвестный товар: {product_name}")
        return jsonify({"status": "unknown product"}), 200
    
    # 5. Начисляем и уведомляем
    try:
        add_tokens(user_id, tokens_to_add)
        add_tribute_transaction(tx_id, user_id, product_name, tokens_to_add)
        logger.info(f"✅ Tribute: {user_id} оплатил {product_name}, начислено {tokens_to_add} токенов")
        
        # Отправляем уведомление
        import asyncio
        async def send_notify():
            try:
                await bot.send_message(
                    user_id, 
                    f"🎉 <b>Оплата прошла успешно!</b>\\n\\n"
                    f"Вы купили: {product_name}\\n"
                    f"Начислено: <b>+{tokens_to_add} токенов</b>\\n\\n"
                    f"Проверьте баланс: /balance"
                )
            except Exception as e:
                logger.warning(f"⚠️ Не удалось отправить уведомление юзеру {user_id}: {e}")
        
        loop = asyncio.get_event_loop()
        loop.create_task(send_notify())
        
    except Exception as e:
        logger.error(f"❌ Ошибка начисления токенов для {user_id}: {e}")
        return jsonify({"error": "DB error"}), 500
    
    return jsonify({"status": "ok"}), 200

'''

# Вставляем перед def run_flask
if "def run_flask():" in content:
    content = content.replace("def run_flask():", new_webhook + "def run_flask():")
    print("✅ Вебхук добавлен в bot.py")
else:
    print("⚠️ Не найдена функция run_flask, добавляю в конец файла")
    content += "\n\n" + new_webhook

# Убедимся, что импорты для проверки подписи есть (внутри функции они есть, но на всякий случай)
if "import hmac" not in content:
    content = content.replace("import os", "import os, hmac, hashlib")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("🎉 bot.py обновлен!")
