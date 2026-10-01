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


def _build_memory_block(user_id: int) -> str:
    """Собирает блок памяти: имя, факты, хобби, темы."""
    try:
        from utils.user_storage import load_profile
        profile = load_profile(user_id)
        if not profile:
            return ""
        prefs = profile.get("preferences", {})
        lines = []
        if profile.get("name"):
            lines.append(f"Пользователя зовут {profile['name']}.")
        if prefs.get("style"):
            lines.append(f"Любимый стиль: {prefs['style']}.")
        if prefs.get("colors"):
            lines.append(f"Любимые цвета: {prefs['colors']}.")
        if prefs.get("hobbies"):
            lines.append(f"Интересы: {', '.join(prefs['hobbies'])}.")
        if prefs.get("favorite_topics"):
            lines.append(f"Любимые темы: {', '.join(prefs['favorite_topics'])}.")
        if prefs.get("facts"):
            lines.append("Факты о пользователе:")
            for f in prefs["facts"][-10:]:
                lines.append(f"  - {f}")
        if lines:
            return " ".join(lines)
    except Exception as e:
        logger.warning(f"⚠️ Память [{user_id}]: {e}")
    return ""


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

    memory_block = _build_memory_block(user_id) if user_id else ""
    system_prompt = f"Ты — Vertex AI, умный ассистент. Отвечай кратко, до {max_output} слов."
    if memory_block:
        system_prompt += f" Ты знаешь о пользователе: {memory_block} Используй эту информацию, не переспрашивай то, что уже знаешь."

    messages = [{"role": "system", "content": system_prompt}]

    if user_id:
        try:
            from utils.user_storage import get_recent_history
            for msg in get_recent_history(user_id, limit=20):
                role = "user" if msg.get("role") == "user" else "assistant"
                messages.append({"role": role, "content": msg.get("text", "")})
        except Exception as e:
            logger.warning(f"⚠️ История [{user_id}]: {e}")

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

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M")
    today_str = now.strftime("%Y-%m-%d")
    tomorrow_str = (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).strftime("%Y-%m-%d")

    memory_block = _build_memory_block(user_id) if user_id else ""

    system_prompt = f"""Ты — ИИ-ассистент Telegram-бота. Определи, что хочет пользователь.

СЕЙЧАС: {now_str} ({today_str}).
ЗАВТРА: {tomorrow_str}.
{f"О ПОЛЬЗОВАТЕЛЕ: {memory_block}" if memory_block else ""}

Верни ТОЛЬКО JSON:
{{"action": "действие", "params": {{...}}}}

Действия:
- generate_image: params: {{"prompt": "..."}}
- show_prices, show_balance, show_referral, show_profile, show_help
- set_reminder: params: {{"text": "...", "time": "HH:MM", "date": "YYYY-MM-DD", "need_clarification": true/false, "question": "..."}}
- list_reminders
- delete_reminder: params: {{"text": "..."}}
- delete_all_reminders
- search_web: params: {{"query": "..."}}
- remember: запомнить ЛЮБОЙ факт о пользователе. params: {{"fact": "пользователь любит кофе и трактора на 5 колёсах"}}
- chat

ПРАВИЛА ДЛЯ set_reminder:
1. Если пользователь просит напомнить и не указал текст — need_clarification: true, question: "Что напомнить?"
2. Если не указано время — need_clarification: true, question: "Во сколько напомнить?"
3. Если не указан день — need_clarification: true, question: "На какой день? Сегодня, завтра или дата?"
4. Только когда есть ВСЕ три поля (текст, время, день) — need_clarification: false.
5. Если пользователь ответил на уточнение — верни обновлённые параметры с need_clarification по остатку.

ПРАВИЛА ДЛЯ remember:
- Если пользователь говорит "я люблю X", "мне нравится X", "я занимаюсь X", "у меня есть X", "я живу в X", "мне X лет" и т.д. — верни action="remember" с фактом в params.fact.
- Факт формулируй как "пользователь любит кофе и трактора на 5 колёсах" — целым предложением.
- НЕ используй ключи hobbies/colors/style — только fact.

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


def generate_ack(fact: str) -> str:
    """Живой ответ на запоминание факта через ИИ."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "Запомнил 😊"

    model = get_model_setting("prompt_enhance") or "gpt-4.1-nano"
    try:
        resp = requests.post(
            "https://openai.bothub.chat/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "Ответь живо и коротко (1 предложение, до 12 слов) на то, что пользователь рассказал о себе. Без ** и markdown. Пример: 'Круто! Кофе и трактора — запомнил 😄'"},
                    {"role": "user", "content": f"Пользователь: {fact}"}
                ],
                "max_tokens": 60,
                "temperature": 0.8
            },
            timeout=15
        )
        if resp.status_code == 200:
            return resp.json().get('choices', [{}])[0].get('message', {}).get('content', '').strip()
    except Exception as e:
        logger.warning(f"⚠️ generate_ack: {e}")
    return "Запомнил 😊"
