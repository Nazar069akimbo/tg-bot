import requests
import json

API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjgzYjE2N2EwLTM1NjItNDhhNi1hNWJkLWEyM2VlYThlNzM3NiIsImlzRGV2ZWxvcGVyIjp0cnVlLCJpYXQiOjE3ODIxOTg5NTIsImV4cCI6MjA5Nzc3NDk1MiwianRpIjoid2ltMGJDaWlLTDluVmppNSJ9.4xwAcU_bVq8iNL46ZxJ0FyWS5CMdAH8km59nfTL5rNE"

models = ["flux-schnell", "gpt-image-2", "gemini-3.1-flash-image"]

for model in models:
    print(f"🧪 Тестирую {model}...")
    resp = requests.post(
        "https://openai.bothub.chat/v1/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 1
        },
        timeout=10
    )
    
    if resp.status_code == 200:
        print(f"  ✅ {model} — ДОСТУПНА")
    else:
        print(f"  ❌ {model} — {resp.status_code}: {resp.text[:100]}")
    print()
