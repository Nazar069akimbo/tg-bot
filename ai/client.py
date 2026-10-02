import os
import json
import re
import logging
import requests
from datetime import datetime, timedelta
from openai import OpenAI
from database.db import get_setting, get_model_setting

logger = logging.getLogger(__name__)

ADMIN_EMAIL = "mychannell@gmail.com"


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
    try:
        from utils.user_storage import load_profile
        profile = load_profile(user_id)
        if not profile:
            return ""
        prefs = profile.get("preferences", {})
        lines = []
        if profile.get("name"):
            lines.append(f"Пользователя зовут {profile['name']}.")
        if prefs.get("facts"):
            for f in prefs["facts"][-10:]:
                lines.append(f"- {f}")
        if lines:
            return " ".join(lines)
    except Exception as e:
        logger.warning(f"⚠️ Память [{user_id}]: {e}")
    return ""


def solve_problem(question, mode="chat", is_premium=False, user_id=None):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "⚠️ Сервис временно недоступен. Напиши админу: " + ADMIN_EMAIL

    client = get_openai_client()
    if not client:
        return "⚠️ Сервис временно недоступен. Напиши админу: " + ADMIN_EMAIL

    max_input = int(get_setting('premium_input_chars' if is_premium else 'free_input_chars') or (3000 if is_premium else 500))
    max_output = int(get_setting('premium_output_words' if is_premium else 'free_output_words') or (300 if is_premium else 50))

    if len(question) > max_input:
        return f"⚠️ Превышен лимит ({len(question)}/{max_input})"

    model = get_model_setting("text_chat") or "deepseek-v4-flash"

    memory_block = _build_memory_block(user_id) if user_id else ""
    system_prompt = "Ты — Vertex AI, дружелюбный ассистент. Отвечай кратко, 1-3 предложения."
    if memory_block:
        system_prompt += f" Ты знаешь о пользователе: {memory_block}"
    system_prompt += " Не используй markdown и звёздочки."

    messages = [{"role": "system", "content": system_prompt}]

    if user_id:
        try:
            from utils.user_storage import get_recent_history
            for msg in get_recent_history(user_id, limit=10):
                role = "user" if msg.get("role") == "user" else "assistant"
                messages.append({"role": role, "content": msg.get("text", "")})
        except Exception as e:
            logger.warning(f"⚠️ История [{user_id}]: {e}")

    messages.append({"role": "user", "content": question})

    def _try_model(m):
        try:
            resp = client.chat.completions.create(
                model=m,
                messages=messages,
                max_tokens=min(max_output * 2, 800),
                temperature=0.7
            )
            choice = resp.choices[0]
            msg = choice.message

            content = getattr(msg, "content", None)
            if content and content.strip():
                return content.strip()

            reasoning = getattr(msg, "reasoning_content", None)
            if reasoning and reasoning.strip():
                return reasoning.strip()

            logger.warning(f"⚠️ {m}: пустой ответ")
            return None
        except Exception as e:
            logger.error(f"❌ {m}: {e}")
            return None

    # Пробуем основную и альтернативные модели
    for m in [model, "gpt-4.1-nano", "gpt-4.1-mini", "deepseek-v4-pro"]:
        logger.info(f"🧪 Пробуем {m}")
        answer = _try_model(m)
        if answer:
            # Сохраняем в историю
            if user_id:
                try:
                    from utils.user_storage import append_history
                    append_history(user_id, "user", question)
                    append_history(user_id, "assistant", answer)
                except Exception as e:
                    logger.warning(f"⚠️ История [{user_id}]: {e}")
            return answer

    # Все модели упали
    logger.error("❌ Все модели не ответили")
    return "😔 Не смог ответить. Попробуй ещё раз или напиши админу: " + ADMIN_EMAIL


def analyze_intent(user_id, text, reminder_state=None):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "chat", {}

    model = get_model_setting("prompt_enhance") or "gpt-4.1-nano"

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M (%A)")
    today_str = now.strftime("%Y-%m-%d")
    tomorrow_str = (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).strftime("%Y-%m-%d")

    memory_block = _build_memory_block(user_id) if user_id else ""

    reminder_context = ""
    if reminder_state:
        reminder_context = f"""
АКТИВНЫЙ ДИАЛОГ НАПОМИНАНИЯ:
Собрано: text={reminder_state.get('text', '')!r}, time={reminder_state.get('time', '')!r}, date={reminder_state.get('date', '')!r}
Последний вопрос: {reminder_state.get('question', '')!r}
"""

    system_prompt = f"""Ты — ИИ-ассистент Telegram-бота. Определи, что хочет пользователь.

СЕЙЧАС: {now_str}.
СЕГОДНЯ: {today_str}. ЗАВТРА: {tomorrow_str}.
{f"О ПОЛЬЗОВАТЕЛЕ: {memory_block}" if memory_block else ""}
{reminder_context}

Верни ТОЛЬКО JSON:
{{"action": "действие", "params": {{...}}}}

Действия:
- generate_image: params: {{"prompt": "..."}}
- show_prices, show_balance, show_referral, show_profile, show_help
- set_reminder: params: {{"text": "...", "time": "HH:MM", "date": "YYYY-MM-DD", "need_clarification": true/false, "question": "..."}}
- cancel_reminder
- list_reminders, delete_reminder: params: {{"text": "..."}}, delete_all_reminders
- search_web: params: {{"query": "..."}}
- remember: params: {{"fact": "..."}}
- chat

ОСОБЫЕ ПРАВИЛА ДЛЯ set_reminder:
1. Невалидное время — need_clarification=true, question="Во сколько напомнить? Например: 18:30"
2. "12.00", "12:00" → time="12:00"
3. "завтра" → date="tomorrow", "сегодня" → date="today"
4. "12 сентября" → date="YYYY-09-12"
5. Если всё собрано — need_clarification=false

ПОРЯДОК ВОПРОСОВ:
- Нет text → "Что напомнить?"
- Нет time → "Во сколько напомнить?"
- Нет date → "На какой день?"

ПРАВИЛА remember:
- "я люблю X", "меня зовут X" → remember с fact.

Отвечай ТОЛЬКО JSON."""

    try:
        resp = requests.post(
            "https://openai.bothub.chat/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Запрос: {text}"}
                ],
                "max_tokens": 400,
                "temperature": 0.2
            },
            timeout=15
        )
        if resp.status_code == 200:
            result = resp.json().get('choices', [{}])[0].get('message', {}).get('content', '{}')
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return data.get('action', 'chat'), data.get('params', {})
        logger.error(f"❌ GPT: {resp.status_code}")
    except Exception as e:
        logger.error(f"❌ Анализ: {e}")

    return 'chat', {}


def search_web(query):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "⚠️ Сервис недоступен"

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
            content = resp.json().get('choices', [{}])[0].get('message', {}).get('content', '')
            return content.strip() if content else "Не нашёл информации."
        return f"❌ Ошибка: {resp.status_code}"
    except Exception as e:
        logger.error(f"❌ Поиск: {e}")
        return "Не смог найти информацию."


def generate_ack(fact: str) -> str:
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
                    {"role": "system", "content": "Ответь живо, 1 предложение, до 12 слов. Без markdown."},
                    {"role": "user", "content": f"Пользователь: {fact}"}
                ],
                "max_tokens": 60,
                "temperature": 0.8
            },
            timeout=15
        )
        if resp.status_code == 200:
            content = resp.json().get('choices', [{}])[0].get('message', {}).get('content', '')
            return content.strip() if content else "Запомнил 😊"
    except Exception as e:
        logger.warning(f"⚠️ generate_ack: {e}")
    return "Запомнил 😊"
