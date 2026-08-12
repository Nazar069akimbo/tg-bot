import re

with open('handlers.py', 'r') as f:
    content = f.read()

# НОВЫЙ СПИСОК МОДЕЛЕЙ (ТОЛЬКО 2)
new_models = '''IMAGE_MODELS = {
    "flux": {
        "name": "🖼️ Flux Schnell",
        "price": 10,
        "api_model": "flux-schnell",
        "type": "replicate",
        "description": "Быстрая, базовая"
    },
    "flux_2_max": {
        "name": "🔥 Flux-2-Max",
        "price": 60,
        "api_model": "flux-2-max",
        "type": "openai",
        "description": "⭐ ТОПОВОЕ КАЧЕСТВО"
    }
}'''

# НОВАЯ СТАТИСТИКА
new_stats = '''model_stats = {
    "flux": 0,
    "flux_2_max": 0
}'''

# ЗАМЕНЯЕМ
content = re.sub(r'IMAGE_MODELS = \{.*?\}', new_models, content, flags=re.DOTALL)
content = re.sub(r'model_stats = \{.*?\}', new_stats, content, flags=re.DOTALL)

with open('handlers.py', 'w') as f:
    f.write(content)

print("✅ handlers.py обновлён: только Flux Schnell + Flux-2-Max")
print("📌 Цены: Flux Schnell — 10 токенов, Flux-2-Max — 60 токенов")
