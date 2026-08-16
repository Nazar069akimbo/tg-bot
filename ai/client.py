import os
from openai import OpenAI
from database.db import get_setting
import logging

logger = logging.getLogger(__name__)

def get_openai_client():
    """Возвращает клиента OpenAI, создавая его при первом вызове."""
    api_key = os.getenv("OPENAI_API_KEY")
    
    # Логируем для отладки
    logger.info(f"🔑 API_KEY присутствует: {bool(api_key)}")
    
    if not api_key:
        logger.error("❌ OPENAI_API_KEY не найден в переменных окружения")
        return None
    
    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://openai.bothub.chat/v1"
        )
        logger.info("✅ OpenAI клиент создан успешно")
        return client
    except Exception as e:
        logger.error(f"❌ Ошибка создания клиента OpenAI: {e}")
        return None

def solve_problem(question, mode="chat", is_premium=False):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("❌ OPENAI_API_KEY отсутствует в solve_problem")
        return "⚠️ API ключ не настроен. Проверьте переменную OPENAI_API_KEY на Render."
    
    client = get_openai_client()
    if not client:
        logger.error("❌ Клиент OpenAI не создан")
        return "⚠️ Ошибка инициализации OpenAI клиента. Проверьте API ключ."
    
    max_input = int(get_setting('premium_input_chars' if is_premium else 'free_input_chars') or (3000 if is_premium else 500))
    max_output = int(get_setting('premium_output_words' if is_premium else 'free_output_words') or (300 if is_premium else 50))
    
    if len(question) > max_input:
        return f"⚠️ Превышен лимит ({len(question)}/{max_input})"
    
    try:
        logger.info(f"📤 Отправка запроса в OpenAI: {question[:50]}...")
        resp = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[
                {"role": "system", "content": f"Ты ассистент. Отвечай кратко, до {max_output} слов."},
                {"role": "user", "content": question}
            ],
            max_tokens=min(max_output * 2, 1000),
            temperature=0.5
        )
        answer = resp.choices[0].message.content
        logger.info(f"✅ Ответ получен: {answer[:50]}...")
        return answer
    except Exception as e:
        logger.error(f"❌ Ошибка OpenAI: {e}")
        return f"⚠️ Ошибка: {str(e)[:100]}"
