import requests
import json
import os

API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjgzYjE2N2EwLTM1NjItNDhhNi1hNWJkLWEyM2VlYThlNzM3NiIsImlzRGV2ZWxvcGVyIjp0cnVlLCJpYXQiOjE3ODIxOTg5NTIsImV4cCI6MjA5Nzc3NDk1MiwianRpIjoid2ltMGJDaWlLTDluVmppNSJ9.4xwAcU_bVq8iNL46ZxJ0FyWS5CMdAH8km59nfTL5rNE"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

print("🔍 Загружаю список моделей из Bothub...")
print("=" * 60)

try:
    resp = requests.get(
        "https://openai.bothub.chat/v1/models",
        headers=headers,
        timeout=10
    )
    
    if resp.status_code == 200:
        data = resp.json()
        models = data.get('data', [])
        
        # Фильтруем модели для картинок
        image_models = []
        for m in models:
            m_id = m.get('id', '').lower()
            if any(keyword in m_id for keyword in ['flux', 'image', 'dall', 'midjourney', 'stable', 'nano', 'gemini', 'banana', 'sdxl']):
                image_models.append(m.get('id'))
        
        print("\n📸 МОДЕЛИ ДЛЯ КАРТИНОК:")
        print("-" * 40)
        for m in sorted(image_models):
            print(f"  ✅ {m}")
        
        print("\n" + "=" * 60)
        print(f"📊 Всего найдено: {len(image_models)} моделей")
    else:
        print(f"❌ Ошибка: {resp.status_code}")
        print(resp.text)

except Exception as e:
    print(f"❌ Ошибка: {e}")
