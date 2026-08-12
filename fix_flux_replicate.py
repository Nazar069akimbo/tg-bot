with open('handlers.py', 'r') as f:
    content = f.read()

# Меняем тип flux_2_max на replicate
old_model = '''    "flux_2_max": {
        "name": "🔥 Flux-2-Max",
        "price": 60,
        "api_model": "flux-2-max",
        "type": "openai",
        "description": "⭐ ТОПОВОЕ КАЧЕСТВО"
    }'''

new_model = '''    "flux_2_max": {
        "name": "🔥 Flux-2-Max",
        "price": 60,
        "api_model": "flux-2-max",
        "type": "replicate",
        "description": "⭐ ТОПОВОЕ КАЧЕСТВО"
    }'''

content = content.replace(old_model, new_model)

# Меняем API endpoint для flux_2_max в generate_image
old_endpoint = '''        if model_config["type"] == "openai":'''
new_endpoint = '''        if model_config["type"] == "openai":
            # OpenAI модели (пока не используются)
            await status_msg.edit_text("❌ OpenAI модели временно отключены")
            return'''

content = content.replace(old_endpoint, new_endpoint)

with open('handlers.py', 'w') as f:
    f.write(content)

print("✅ Flux-2-Max переключен на Replicate API")
