from openai import OpenAI
import os

API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjgzYjE2N2EwLTM1NjItNDhhNi1hNWJkLWEyM2VlYThlNzM3NiIsImlzRGV2ZWxvcGVyIjp0cnVlLCJpYXQiOjE3ODIxOTg5NTIsImV4cCI6MjA5Nzc3NDk1MiwianRpIjoid2ltMGJDaWlLTDluVmppNSJ9.4xwAcU_bVq8iNL46ZxJ0FyWS5CMdAH8km59nfTL5rNE"

client = OpenAI(
    api_key=API_KEY,
    base_url='https://openai.bothub.chat/v1'
)

print("🧪 Тестирую gemini-2.5-flash-lite...")

try:
    # 1. Проверка текста
    response = client.chat.completions.create(
        model='gemini-2.5-flash-lite',
        messages=[{"role": "user", "content": "Say hello"}],
        max_tokens=20
    )
    print(f"✅ Текст работает: {response.choices[0].message.content}")

    # 2. Проверка картинки
    params = {
        'model': 'gemini-2.5-flash-lite',
        'prompt': 'a cute cat',
        'n': 1,
        'size': '1024x1024',
    }
    req = client.images.generate(**params)
    import json
    img_url = json.loads(req.model_dump_json())['data'][0]['url']
    print(f"✅ Картинка сгенерирована: {img_url}")
    
except Exception as e:
    print(f"❌ Ошибка: {e}")
