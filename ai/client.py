import os
import json
import re
import logging
import requests
from openai import OpenAI
from database.db import get_setting, get_model_setting

logger = logging.getLogger(__name__)


def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("❌ OPENAI_API_KEY не найден")
        return None
    try:
        client = OpenAI(api_key=api_key, base_url="https://openai.bothub.chat/v1")
        return client
    except Exception as e:
        logger.error(f"❌ Ошибка клиента: {e}")
        return None


def solve_problem(question, mode="chat", is_premium=False, user_id=None):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "⚠️ API ключ не настроен"

    client = get_openai_client()
    if not client:
        return "⚠️ Ошибка инициализации OpenAI"

    max_input = int(get_setting('premium_input_chars' if is_premium else 'free_input_chars') or (3000 if is_premium else 500))
    max_output = int(get_setting('premium_output_words' if is_premium else 'free_output_words') or (300 if is_premium else 50))

    if len(question) > max_input:
        return f"⚠️ Превышен лимит ({len(question)}/{max_input})"

    model = get_model_setting("text_chat") or "deepseek-v4-flash"

    system_prompt = f"Ты ассистент. Отвечай кратко, до {max_output} слов."
    messages = [{"role": "system", "content": system_prompt}]

    if user_id:
        try:
            from utils.user_storage import load_profile, get_recent_history
            profile = load_profile(user_id)
            name = profile.get("name")
            prefs = profile.get("preferences", {})

            lines = []
            if name:
                lines.append(f"Пользователя зовут {name}.")
            if prefs.get("style"):
                lines.append(f"Любимый стиль: {prefs['style']}.")
            if prefs.get("colors"):
                lines.append(f"Любимые цвета: {prefs['colors']}.")
            if prefs.get("hobbies"):
                lines.append(f"Хобби: {', '.join(prefs['hobbies'])}.")
            if prefs.get("favorite_topics"):
                lines.append(f"Любимые темы: {', '.join(prefs['favorite_topics'])}.")
            if lines:
                messages[0]["content"] += " " + " ".join(lines)

            for msg in get_recent_history(user_id, limit=20):
                role = "user" if msg.get("role") == "user" else "assistant"
                messages.append({"role": role, "content": msg.get("text", "")})
        except Exception as e:
            logger.warning(f"⚠️ Память [{user_id}]: {e}")

    messages.append({"role": "user", "content": question})

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=min(max_output * 2, 1000),
            temperature=0.5
        )
        answer = resp.choices[0].message.content

        if user_id:
            try:
                from utils.user_storage import append_history
                append_history(user_id, "user", question)
                append_history(user_id, "assistant", answer)
            except Exception as e:
                logger.warning(f"⚠️ История [{user_id}]: {e}")

        return answer
    except Exception as e:
        logger.error(f"❌ OpenAI: {e}")
        return f"⚠️ Ошибка: {str(e)[:100]}"


def analyze_intent(user_id, text):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "chat", {}

    model = get_model_setting("prompt_enhance") or "gpt-4.1-nano"

    system_prompt = """Ты — ИИ-ассистент Telegram-бота. Определи, что хочет пользователь.

Верни ТОЛЬКО JSON:
{"action": "действие", "params": {...}}

Действия:
- generate_image: создать картинку. params: {"prompt": "..."}
- edit_image: изменить картинку. params: {"prompt": "..."}
- show_prices: цены
- show_balance: баланс
- show_referral: рефералы
- show_profile: профиль
- show_help: помощь
- set_reminder: напомнить. params: {"text": "...", "time": "HH:MM", "date": "YYYY-MM-DD или today/tomorrow", "need_clarification": true/false, "question": "..."}
- list_reminders: список напоминаний
- delete_reminder: удалить напоминание. params: {"text": "..."}
- delete_all_reminders: удалить все
- search_web: поиск в интернете. params: {"query": "..."}
- update_profile: обновить профиль. params: {"key": "hobbies|colors|style|name|favorite_topics", "value": "..."}
- chat: обычный разговор

Правила:
- Если просит напомнить и не указал дату — need_clarification: true, question: "На какой день?"
- Если не указал время — need_clarification: true, question: "Во сколько напомнить?"
- Если говорит о себе ("я люблю...", "меня зовут...", "я занимаюсь...") — update_profile.
- Отвечай ТОЛЬКО JSON."""

    try:
        logger.info(f"🧠 [{user_id}] Анализ: {text[:50]}...")
        resp = requests.post(
            "https://openai.bothub.chat/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Запрос: {text}"}
                ],
                "max_tokens": 200,
                "temperature": 0.1
            },
            timeout=15
        )
        if resp.status_code == 200:
            result = resp.json().get('choices', [{}])[0].get('message', {}).get('content', '{}')
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                action = data.get('action', 'chat')
                params = data.get('params', {})
                logger.info(f"✅ [{user_id}] {action} | {params}")
                return action, params
        else:
            logger.error(f"❌ GPT: {resp.status_code}")
    except Exception as e:
        logger.error(f"❌ Анализ: {e}")

    return 'chat', {}


def search_web(query):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "⚠️ API ключ не настроен"

    model = get_model_setting("text_chat") or "deepseek-v4-flash"

    try:
        logger.info(f"🔍 Поиск: {query[:60]}...")
        resp = requests.post(
            "https://openai.bothub.chat/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "Ты — поисковый ассистент. Найди актуальную информацию и дай краткий ответ."},
                    {"role": "user", "content": query}
                ],
                "max_tokens": 500,
                "temperature": 0.3
            },
            timeout=30
        )
        if resp.status_code == 200:
            return resp.json().get('choices', [{}])[0].get('message', {}).get('content', '❌ Пусто')
        return f"❌ Ошибка: {resp.status_code}"
    except Exception as e:
        logger.error(f"❌ Поиск: {e}")
        return f"❌ Ошибка: {str(e)[:100]}"
