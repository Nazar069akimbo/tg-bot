import requests
import os
import json

API_KEY = os.getenv('OPENAI_API_KEY')

if not API_KEY:
    print("❌ API_KEY не найден! Проверь .env файл")
    exit(1)

print("🔍 Проверяю доступные модели в Bothub...")

try:
    # Вариант 1: через /v1/models (как в OpenAI)
    resp1 = requests.get(
        "https://openai.bothub.chat/v1/models",
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=10
    )
    
    if resp1.status_code == 200:
        data = resp1.json()
        if 'data' in data:
            models = [m['id'] for m in data['data'] if 'image' in m['id'].lower() or 'flux' in m['id'].lower() or 'nano' in m['id'].lower() or 'gemini' in m['id'].lower() or 'banana' in m['id'].lower()]
            print("\n📸 МОДЕЛИ ДЛЯ КАРТИНОК:")
            for m in models:
                print(f"   - {m}")
        else:
            print("   ⚠️ Неожиданный ответ от API")
    else:
        print(f"   ⚠️ Ошибка {resp1.status_code}: {resp1.text}")

except Exception as e:
    print(f"❌ Ошибка: {e}")

print("\n" + "="*50)
print("💡 Ищи в этом списке: flux, nano, gemini, image")
print("="*50)
