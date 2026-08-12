import requests
import json
import os

API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjgzYjE2N2EwLTM1NjItNDhhNi1hNWJkLWEyM2VlYThlNzM3NiIsImlzRGV2ZWxvcGVyIjp0cnVlLCJpYXQiOjE3ODIxOTg5NTIsImV4cCI6MjA5Nzc3NDk1MiwianRpIjoid2ltMGJDaWlLTDluVmppNSJ9.4xwAcU_bVq8iNL46ZxJ0FyWS5CMdAH8km59nfTL5rNE"
API_BASE = "https://openai.bothub.chat/v1"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# Список моделей для проверки
models_to_check = [
    "flux-schnell",
    "flux-1.1-pro",
    "gpt-image-2",
    "gemini-3.1-flash-image",
    "gemini-3-pro-image",
    "qwen-image-3",
    "mai-image-2.5",
    "grok-imagine-image-quality"
]

print("🔍 ПРОВЕРКА ДОСТУПНОСТИ МОДЕЛЕЙ (без траты CAPS)")
print("=" * 60)

for model in models_to_check:
    try:
        # Отправляем HEAD-запрос на эндпоинт модели
        resp = requests.head(
            f"{API_BASE}/models/{model}",
            headers=headers,
            timeout=5
        )
        
        if resp.status_code == 200:
            print(f"✅ {model} — ДОСТУПНА (200 OK)")
        elif resp.status_code == 404:
            print(f"❌ {model} — НЕ НАЙДЕНА (404)")
        elif resp.status_code == 403:
            print(f"🚫 {model} — ЗАПРЕЩЕНО (403) — нужно повысить тариф")
        elif resp.status_code == 401:
            print(f"🔑 {model} — НЕТ АВТОРИЗАЦИИ (401)")
        else:
            print(f"⚠️ {model} — ОТВЕТ {resp.status_code}")
            
    except Exception as e:
        print(f"❌ {model} — ОШИБКА: {str(e)[:50]}")

print("\n" + "=" * 60)
print("💡 Если модель отвечает 200 — она доступна и готова к работе.")
print("💡 Если 403 — нужно купить подписку BASIC или выше.")
