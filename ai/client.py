import os
from openai import OpenAI
from database.db import get_setting

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url="https://openai.bothub.chat/v1")

def solve_problem(question, mode="chat", is_premium=False):
    if not os.getenv("OPENAI_API_KEY"):
        return "⚠️ API ключ не настроен"
    
    max_input = int(get_setting('premium_input_chars' if is_premium else 'free_input_chars') or (3000 if is_premium else 500))
    max_output = int(get_setting('premium_output_words' if is_premium else 'free_output_words') or (300 if is_premium else 50))
    
    if len(question) > max_input:
        return f"⚠️ Превышен лимит ({len(question)}/{max_input})"
    
    try:
        resp = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[{"role": "system", "content": f"Ты ассистент. Отвечай кратко, до {max_output} слов."}, {"role": "user", "content": question}],
            max_tokens=min(max_output * 2, 1000),
            temperature=0.5
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"⚠️ Ошибка: {e}"
