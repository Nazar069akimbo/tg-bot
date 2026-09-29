import os
import json
import re
import logging
import requests
from datetime import datetime, timedelta
from openai import OpenAI
from database.db import get_setting, get_model_setting

logger = logging.getLogger(__name__)


def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("❌ OPENAI_API_KEY не найден")
        return None
    try:
        return OpenAI(api_key=api_key, base_url="https://openai.bothub.chat/v1")
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
    """Разбор намерения. ИИ сам восстанавливает дату/время из текста."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "chat", {}

    model = get_model_setting("prompt_enhance") or "gpt-4.1-nano"

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M")
    today_str = now.strftime("%Y-%m-%d")
    tomorrow_str = (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).strftime("%Y-%m-%d")

    system_prompt = f"""Ты — ИИ-ассистент Telegram-бота. Определи, что хочет пользователь.

СЕЙЧАС: {now_str} ({today_str}).
ЗАВТРА: {tomorrow_str}.

Верни ТОЛЬКО JSON:
{{"action": "действие", "params": {{...}}}}

Действия:
- generate_image: создать картинку. params: {{"prompt": "..."}}
- show_prices, show_balance, show_referral, show_profile, show_help
- set_reminder: напомнить. params: {{"text": "...", "time": "HH:MM", "date": "YYYY-MM-DD", "need_clarification": true/false, "question": "..."}}
- list_reminders: список напоминаний
- delete_reminder: удалить. params: {{"text": "..."}}
- delete_all_reminders: удалить все
- search_web: поиск. params: {{"query": "..."}}
- update_profile: обновить профиль. params: {{"key": "hobbies|colors|style|name|favorite_topics", "value": "..."}}
- chat: разговор

ПРАВИЛА для set_reminder:
1. "через N минут" → time = "через N минут".
2. "в HH:MM" → time = "HH:MM".
3. "завтра" → date = "tomorrow". "сегодня" → date = "today".
4. "25 числа" или "25.09" → date = "YYYY-MM-DD".
5. Если не указан текст → need_clarification: true, question: "Что напомнить?"
6. Если не указано время → need_clarification: true, question: "Во сколько напомнить?"
7. Если пользователь отвечает просто "завтра" на вопрос "во сколько?" — это ответ про ДАТУ, а не время. Верни date = "tomorrow", need_clarification: true, question: "Во сколько?"
8. Если отвечает "18:03" — это ВРЕМЯ.

ПРАВИЛА для update_profile:
Если пользователь говорит "я люблю...", "меня зовут...", "я занимаюсь..." — сохрани это в профиль.

Отвечай ТОЛЬКО JSON, без пояснений."""

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
                "max_tokens": 300,
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
