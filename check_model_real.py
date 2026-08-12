import requests
import json
import time

API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjgzYjE2N2EwLTM1NjItNDhhNi1hNWJkLWEyM2VlYThlNzM3NiIsImlzRGV2ZWxvcGVyIjp0cnVlLCJpYXQiOjE3ODIxOTg5NTIsImV4cCI6MjA5Nzc3NDk1MiwianRpIjoid2ltMGJDaWlLTDluVmppNSJ9.4xwAcU_bVq8iNL46ZxJ0FyWS5CMdAH8km59nfTL5rNE"
API_BASE = "https://openai.bothub.chat/v1"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

models = [
    "flux-schnell",
    "flux-1.1-pro",
    "gpt-image-2",
    "gemini-3.1-flash-image",
    "gemini-3-pro-image",
    "qwen-image-3",
    "mai-image-2.5"
]

print("🔍 ПРОВЕРКА МОДЕЛЕЙ (минимальный запрос)")
print("=" * 60)

for model in models:
    try:
        # Пробуем получить информацию о модели через chat completion (без реальной генерации)
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "test"}],
            "max_tokens": 1
        }
        
        start = time.time()
        resp = requests.post(
            f"{API_BASE}/chat/completions",
            headers=headers,
            json=payload,
            timeout=10
        )
        elapsed = time.time() - start
        
        if resp.status_code == 200:
            print(f"✅ {model} — ДОСТУПНА ({elapsed:.2f}с)")
        elif resp.status_code == 404:
            print(f"❌ {model} — НЕ НАЙДЕНА (404)")
        elif resp.status_code == 403:
            print(f"🚫 {model} — ЗАПРЕЩЕНО (нужна подписка)")
        elif resp.status_code == 401:
            print(f"🔑 {model} — НЕТ АВТОРИЗАЦИИ")
        elif resp.status_code == 429:
            print(f"⏳ {model} — ЛИМИТ ЗАПРОСОВ")
        else:
            # Если ошибка с моделью — считаем что она есть, но не работает
            if "model" in resp.text.lower():
                print(f"✅ {model} — ВИДИМА (код {resp.status_code})")
            else:
                print(f"⚠️ {model} — {resp.status_code}")
                
    except Exception as e:
        print(f"❌ {model} — ОШИБКА: {str(e)[:50]}")

print("\n" + "=" * 60)
print("💡 200 = модель работает")
print("💡 404 = модель не найдена в Bothub")
print("💡 403 = нужна подписка BASIC или выше")
