import requests
import os

BOTHUB_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjgzYjE2N2EwLTM1NjItNDhhNi1hNWJkLWEyM2VlYThlNzM3NiIsImlzRGV2ZWxvcGVyIjp0cnVlLCJpYXQiOjE3ODIxOTg5NTIsImV4cCI6MjA5Nzc3NDk1MiwianRpIjoid2ltMGJDaWlLTDluVmppNSJ9.4xwAcU_bVq8iNL46ZxJ0FyWS5CMdAH8km59nfTL5rNE"

headers = {
    "Authorization": f"Bearer {BOTHUB_API_KEY}",
    "Content-Type": "application/json"
}

print("🔍 Проверяем доступные модели...\n")

# 1. Список всех моделей
url = "https://openai.bothub.chat/v1/models"
response = requests.get(url, headers=headers)

if response.status_code == 200:
    data = response.json()
    models = data.get('data', [])
    
    print("📋 ДОСТУПНЫЕ МОДЕЛИ:\n")
    for m in models:
        model_id = m.get('id', 'unknown')
        print(f"  ✅ {model_id}")
else:
    print(f"❌ Ошибка получения списка моделей: {response.status_code}")
    print(response.text)

print("\n" + "="*50 + "\n")

# 2. Проверка генерации картинок
print("🎨 Проверяем доступ к генерации картинок...\n")

test_prompt = "a cat"
url = "https://openai.bothub.chat/v1/images/generations"
data = {
    "model": "dall-e-2",
    "prompt": test_prompt,
    "n": 1,
    "size": "256x256"
}

response = requests.post(url, headers=headers, json=data, timeout=30)

if response.status_code == 200:
    print("✅ Доступ к генерации картинок ЕСТЬ!")
    print(f"   Ответ: {response.json()}")
elif response.status_code == 403:
    print("❌ НЕТ доступа к генерации картинок (403)")
    print("   Возможно, нужно пополнить баланс или подключить услугу")
elif response.status_code == 404:
    print("❌ Эндпоинт не найден (404)")
    print("   Возможно, генерация картинок недоступна на вашем тарифе")
else:
    print(f"⚠️ Ошибка: {response.status_code}")
    print(f"   {response.text}")
