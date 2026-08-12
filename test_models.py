import requests
import json

API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjgzYjE2N2EwLTM1NjItNDhhNi1hNWJkLWEyM2VlYThlNzM3NiIsImlzRGV2ZWxvcGVyIjp0cnVlLCJpYXQiOjE3ODIxOTg5NTIsImV4cCI6MjA5Nzc3NDk1MiwianRpIjoid2ltMGJDaWlLTDluVmppNSJ9.4xwAcU_bVq8iNL46ZxJ0FyWS5CMdAH8km59nfTL5rNE"

models = [
    "gpt-image-1.5",
    "qwen-image-3",
    "grok-imagine-image-quality",
    "midjourney",
    "dall-e-3"
]

for model in models:
    print(f"🧪 Тестирую {model}...")
    resp = requests.post(
        "https://openai.bothub.chat/v1/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": "cat"}],
            "max_tokens": 1
        },
        timeout=5
    )
    if resp.status_code == 200:
        print(f"  ✅ {model} — РАБОТАЕТ")
    else:
        print(f"  ❌ {model} — {resp.status_code}: {resp.text[:80]}")
