import os
from openai import OpenAI
from dotenv import load_dotenv
from database.db import get_setting

load_dotenv()

# Проверяем наличие API ключа
API_KEY = os.getenv("BOTHUB_API_KEY")
if not API_KEY:
    print("⚠️ BOTHUB_API_KEY не найден в .env файле!")

client = OpenAI(
    api_key=API_KEY,
    base_url="https://openai.bothub.chat/v1"
)

def solve_problem(question, mode="gdz", is_premium=False):
    """Решение задачи через AI"""
    if not API_KEY:
        return "⚠️ Ошибка: API ключ не настроен. Проверьте .env файл."
    
    if is_premium:
        max_input = int(get_setting('premium_input_chars') or 3000)
        max_output = int(get_setting('premium_output_words') or 300)
    else:
        max_input = int(get_setting('free_input_chars') or 500)
        max_output = int(get_setting('free_output_words') or 50)
    
    if len(question) > max_input:
        return f"⚠️ Превышен лимит символов ({len(question)}/{max_input})"
    
    if mode == "chat":
        prompt = f"Ты дружелюбный ассистент. Отвечай кратко, максимум {max_output} слов."
    else:
        prompt = f"Ты репетитор по математике. Решай задачи кратко, максимум {max_output} слов."
    
    try:
        max_tokens = max_output * 2
        if max_tokens < 50:
            max_tokens = 50
        if max_tokens > 1000:
            max_tokens = 1000
        
        resp = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": question}
            ],
            max_tokens=max_tokens,
            temperature=0.7 if mode == "chat" else 0.3
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"⚠️ Ошибка AI: {str(e)}"
