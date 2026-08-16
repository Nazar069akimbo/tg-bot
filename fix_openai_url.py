import re

with open('handlers.py', 'r') as f:
    content = f.read()

# ===== 1. ИЩЕМ ПРОБЛЕМНЫЙ КОД =====
old_code = """            image_url = json.loads(req.model_dump_json())['data'][0]['url']
            log_info(user_id, "generate_image", f"Скачивание картинки...")
            if image_url:"""

new_code = """            # Получаем URL картинки (безопасно)
            if hasattr(req, 'data') and len(req.data) > 0:
                image_url = req.data[0].url
                log_info(user_id, "generate_image", f"URL получен: {image_url[:50]}...")
            else:
                log_error(user_id, "generate_image", "Нет data в ответе OpenAI")
                image_url = None
            
            if image_url:
                log_info(user_id, "generate_image", f"Скачивание картинки...")"""

# ===== 2. ЗАМЕНЯЕМ =====
if old_code in content:
    content = content.replace(old_code, new_code)
    print("✅ Код заменён на безопасную версию")
else:
    print("⚠️ Старый код не найден, пробуем альтернативный вариант...")
    
    # Альтернативный поиск
    old_code_alt = """image_url = json.loads(req.model_dump_json())['data'][0]['url']"""
    if old_code_alt in content:
        content = content.replace(old_code_alt, """# Получаем URL картинки (безопасно)
            if hasattr(req, 'data') and len(req.data) > 0:
                image_url = req.data[0].url
                log_info(user_id, "generate_image", f"URL получен: {image_url[:50]}...")
            else:
                log_error(user_id, "generate_image", "Нет data в ответе OpenAI")
                image_url = None""")
        print("✅ Альтернативная замена выполнена")
    else:
        print("❌ Код не найден! Проверь handlers.py")

# ===== 3. ДОБАВЛЯЕМ ОБРАБОТКУ ОШИБОК СКАЧИВАНИЯ =====
old_download = """                img_data_response = requests.get(image_url, timeout=30)
                if img_data_response.status_code == 200 and len(img_data_response.content) > 1000:
                    img_data = img_data_response.content
                    log_info(user_id, "generate_image", f"Картинка скачана, размер: {len(img_data)} байт")"""

new_download = """                img_data_response = requests.get(image_url, timeout=30)
                if img_data_response.status_code == 200 and len(img_data_response.content) > 1000:
                    img_data = img_data_response.content
                    log_info(user_id, "generate_image", f"Картинка скачана, размер: {len(img_data)} байт")
                else:
                    log_error(user_id, "generate_image", f"Ошибка скачивания: {img_data_response.status_code}, размер: {len(img_data_response.content)}")"""

if old_download in content:
    content = content.replace(old_download, new_download)
    print("✅ Добавлена обработка ошибок скачивания")
else:
    print("⚠️ Блок скачивания не найден")

# ===== 4. СОХРАНЯЕМ =====
with open('handlers.py', 'w') as f:
    f.write(content)

print("\n📊 ИЗМЕНЕНИЯ ПРИМЕНЕНЫ!")

# ===== 5. ПРОВЕРКА =====
print("\n🔍 ПРОВЕРКА ИЗМЕНЕНИЙ:")
with open('handlers.py', 'r') as f:
    content = f.read()

checks = [
    ("hasattr(req, 'data')", "✅ hasattr(req, 'data') найден"),
    ("req.data[0].url", "✅ req.data[0].url найден"),
    ("image_url = None", "✅ image_url = None найден"),
    ("Ошибка скачивания", "✅ Обработка ошибок скачивания найдена")
]

for check, msg in checks:
    if check in content:
        print(f"  {msg}")
    else:
        print(f"  ❌ {check} НЕ НАЙДЕН!")

print("\n✅ Скрипт выполнен!")
