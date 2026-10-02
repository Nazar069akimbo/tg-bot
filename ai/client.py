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

INTENT_MODEL = "gpt-4.1-nano"  # всегда для разбора


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


def _get_user_context(user_id: int):
    try:
        from utils.user_storage import load_profile, get_recent_history
        profile = load_profile(user_id)
        prefs = profile.get("preferences", {}) if profile else {}
        lines = []
        if profile.get("name"):
            lines.append(f"Имя: {profile['name']}")
        facts = prefs.get("facts", [])
        if facts:
            lines.append("Факты:")
            for f in facts[-15:]:
                lines.append(f"  - {f}")
        history = get_recent_history(user_id, limit=10)
        return "\n".join(lines), history
    except Exception as e:
        logger.warning(f"⚠️ Контекст [{user_id}]: {e}")
        return "", []


def _try_model(client, m, messages, max_tokens=600):
    try:
        resp = client.chat.completions.create(
            model=m, messages=messages, max_tokens=max_tokens, temperature=0.3
        )
        choice = resp.choices[0]
        msg_obj = choice.message
        content = getattr(msg_obj, "content", None)
        if content and content.strip():
            return content.strip()
        reasoning = getattr(msg_obj, "reasoning_content", None)
        if reasoning and reasoning.strip():
            return reasoning.strip()
        return None
    except Exception as e:
        logger.error(f"❌ {m}: {e}")
        return None


def _fallback_models(primary):
    """Список fallback-моделей."""
    all_models = [primary, "gpt-4.1-nano", "deepseek-v4-flash", "gpt-4.1-mini"]
    seen = set()
    result = []
    for m in all_models:
        if m and m not in seen:
            seen.add(m)
            result.append(m)
    return result


def smart_reply(user_id: int, text: str, reminder_state: dict = None) -> dict:
    """Разбор намерения (дешёвой) + ответ (выбранной моделью)."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"action": "reply", "reply": "⚠️ Сервис недоступен. Напиши админу: " + ADMIN_EMAIL}

    client = get_openai_client()
    if not client:
        return {"action": "reply", "reply": "⚠️ Сервис недоступен. Напиши админу: " + ADMIN_EMAIL}

    user_model = get_model_setting("text_chat") or "gpt-4.1-nano"

    context, history = _get_user_context(user_id)

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M (%A)")
    today_str = now.strftime("%Y-%m-%d")
    tomorrow_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    reminder_context = ""
    if reminder_state:
        reminder_context = f"""
АКТИВНЫЙ ДИАЛОГ НАПОМИНАНИЯ (НЕ переспрашивай заполненные поля!):
- text: {reminder_state.get('text', '')!r}
- time: {reminder_state.get('time', '')!r}
- date: {reminder_state.get('date', '')!r}
Последний вопрос: {reminder_state.get('question', '')!r}
"""

    system_prompt = f"""Ты — ИИ-ассистент Telegram-бота. Верни ТОЛЬКО JSON.

СЕЙЧАС: {now_str}
СЕГОДНЯ: {today_str}, ЗАВТРА: {tomorrow_str}

О ПОЛЬЗОВАТЕЛЕ:
{context if context else "(пока ничего)"}
{reminder_context}

Формат JSON:
{{
  "action": "reply | generate_image | set_reminder | cancel_reminder | delete_reminder | delete_all_reminders | list_reminders | search_web | remember",
  "reply": "текст для пользователя (ВСЕГДА заполняй)",
  "prompt": "...", "text": "...", "time": "HH:MM", "date": "YYYY-MM-DD",
  "need_clarification": true/false, "question": "...",
  "query": "...", "fact": "..."
}}

ДЕЙСТВИЯ:
- reply — ответ. Поле "reply".
- generate_image — картинка. Поле "prompt".
- set_reminder — напоминание. Поля text/time/date.
- remember — запомнить. Поле "fact" И "reply" (живой ответ).
- search_web — поиск. Поле "query".
- delete_reminder / delete_all_reminders / list_reminders / cancel_reminder.

ПРАВИЛА:
1. ВСЕГДА заполняй "reply" — живой текст.
2. При активном напоминании — не переспрашивай уже собранные поля.
3. Невалидное время (24:61) → reply="24:61 — такого времени не существует." + need_clarification=true.
4. "сегодня" → date="today", "завтра" → date="tomorrow".
5. Вопросы о хобби/имени → action="reply", используй "О ПОЛЬЗОВАТЕЛЕ".
6. remember: "я люблю X" → fact="пользователь любит X", reply="Круто! Запомнил 😊".

Отвечай ТОЛЬКО JSON."""

    messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        role = "user" if msg.get("role") == "user" else "assistant"
        messages.append({"role": role, "content": msg.get("text", "")})
    messages.append({"role": "user", "content": text})

    # ШАГ 1: Разбор намерения дешёвой моделью
    raw = None
    for m in _fallback_models(INTENT_MODEL):
        raw = _try_model(client, m, messages)
        if raw:
            break

    if not raw:
        return {"action": "reply", "reply": "😔 Не смог ответить. Попробуй ещё раз."}

    json_match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not json_match:
        return {"action": "reply", "reply": raw}

    try:
        data = json.loads(json_match.group())
    except Exception as e:
        logger.error(f"❌ JSON: {e}")
        return {"action": "reply", "reply": raw}

    action = data.get("action", "reply")

    # ШАГ 2: Если это reply и выбрана другая модель — перегенерируем ответ
    if action == "reply" and user_model and user_model != INTENT_MODEL:
        reply_prompt = f"""Ответь пользователю кратко и живо.

Сообщение пользователя: {text}

Контекст о пользователе:
{context if context else "(нет данных)"}

Ответь 1-3 предложениями, без markdown и звёздочек. Учитывай контекст."""

        messages2 = [
            {"role": "system", "content": "Ты — Vertex AI, дружелюбный ассистент. Отвечай кратко и по делу."},
            {"role": "user", "content": reply_prompt}
        ]

        for m in _fallback_models(user_model):
            answer = _try_model(client, m, messages2, max_tokens=400)
            if answer:
                data["reply"] = answer.strip()
                logger.info(f"🧠 [{user_id}] Ответ от {m}")
                break

    logger.info(f"🧠 [{user_id}] {action} | {data.get('reply', '')[:60]}")
    return data


def search_web(query):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "⚠️ Сервис недоступен"
    client = get_openai_client()
    if not client:
        return "⚠️ Сервис недоступен"

    user_model = get_model_setting("text_chat") or "gpt-4.1-nano"
    messages = [
        {"role": "system", "content": "Ты — поисковый ассистент. Найди актуальную информацию и дай краткий ответ."},
        {"role": "user", "content": query}
    ]
    for m in _fallback_models(user_model):
        answer = _try_model(client, m, messages, max_tokens=500)
        if answer:
            return answer
    return "Не смог найти информацию."
