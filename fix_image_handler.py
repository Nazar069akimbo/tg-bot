with open('handlers.py', 'r') as f:
    content = f.read()

# Находим и исправляем обработку ответа для openai
old = '''                req = client.images.generate(**params)
                image_url = json.loads(req.model_dump_json())['data'][0]['url']
                if image_url:
                    img_data_response = requests.get(image_url, timeout=30)
                    if img_data_response.status_code == 200 and len(img_data_response.content) > 1000:
                        img_data = img_data_response.content'''

new = '''                req = client.images.generate(**params)
                # Получаем URL из ответа
                if hasattr(req, 'data') and len(req.data) > 0:
                    image_url = req.data[0].url
                    if image_url:
                        img_data_response = requests.get(image_url, timeout=30)
                        if img_data_response.status_code == 200 and len(img_data_response.content) > 1000:
                            img_data = img_data_response.content
                else:
                    # fallback: через json
                    resp_json = json.loads(req.model_dump_json())
                    if 'data' in resp_json and len(resp_json['data']) > 0:
                        image_url = resp_json['data'][0]['url']
                        if image_url:
                            img_data_response = requests.get(image_url, timeout=30)
                            if img_data_response.status_code == 200 and len(img_data_response.content) > 1000:
                                img_data = img_data_response.content'''

content = content.replace(old, new)

with open('handlers.py', 'w') as f:
    f.write(content)

print("✅ Исправлен обработчик ответа для Flux-2-Max")
