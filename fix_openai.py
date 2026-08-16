import re

with open('handlers.py', 'r') as f:
    content = f.read()

# ===== 1. ДОБАВЛЯЕМ IMPORT JSON =====
if 'import json' not in content:
    content = content.replace('import json, re', 'import json, re')
    content = content.replace('import json', 'import json')

# ===== 2. ЗАМЕНЯЕМ БЛОК ГЕНЕРАЦИИ КАРТИНКИ =====
old_generate = '''
        img_data = None
        if img_resp.status_code == 200:
            result = img_resp.json()
            img_url = result.get('url')
            if isinstance(img_url, list):
                img_url = img_url[0]
            if img_url:
                log_info(user_id, "generate_image", f"Скачивание картинки с {img_url[:50]}...")
                img_data_response = requests.get(img_url, timeout=30)
                if img_data_response.status_code == 200 and len(img_data_response.content) > 1000:
                    img_data = img_data_response.content
                    log_info(user_id, "generate_image", f"Картинка скачана, размер: {len(img_data)} байт")
'''

new_generate = '''
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
'''

content = content.replace(old_generate, new_generate)

# ===== 3. ЗАМЕНЯЕМ БЛОК ПРАВКИ КАРТИНКИ =====
old_edit = '''
        img_data = None
        if img_resp.status_code == 200:
            result = img_resp.json()
            img_url = result.get('url')
            if isinstance(img_url, list):
                img_url = img_url[0]
            if img_url:
                img_data_response = requests.get(img_url, timeout=30)
                if img_data_response.status_code == 200 and len(img_data_response.content) > 1000:
                    img_data = img_data_response.content
'''

new_edit = '''
        img_data = None
        try:
            # Используем OpenAI клиент для генерации
            params = {
                'model': model_config["api_model"],
                'prompt': enhanced,
                'n': 1,
                'size': '1024x1024',
            }
            req = client.images.generate(**params)
            image_url = json.loads(req.model_dump_json())['data'][0]['url']
            if image_url:
                img_data_response = requests.get(image_url, timeout=30)
                if img_data_response.status_code == 200 and len(img_data_response.content) > 1000:
                    img_data = img_data_response.content
        except Exception as e:
            log_error(user_id, "edit_image", f"OpenAI ошибка: {e}")
            # Пробуем через Replicate
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
'''

content = content.replace(old_edit, new_edit)

with open('handlers.py', 'w') as f:
    f.write(content)

print("✅ Переход на OpenAI клиент выполнен!")
print("📊 Теперь генерация идёт через client.images.generate")
print("🔄 Если OpenAI не работает — автоматически пробует Replicate")
