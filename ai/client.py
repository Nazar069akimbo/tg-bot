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


def _get_user_context(user_id: int) -> str:
    """Собирает всё, что бот знает о пользователе."""
    try:
        from utils.user_storage import load_profile, get_recent_history
        profile = load_profile(user_id)
        prefs = profile.get("preferences", {}) if profile else {}
        lines = []
        if profile.get("name"):
            lines.append(f"Имя: {profile['name']}")
        if prefs.get("hobbies"):
            lines.append(f"Хобби: {', '.join(prefs['hobbies'])}")
        if prefs.get("favorite_topics"):
            lines.append(f"Любимые темы: {', '.join(prefs['favorite_topics'])}")
        if prefs.get("colors"):
            lines.append(f"Любимые цвета: {prefs['colors']}")
        if prefs.get("style"):
            lines.append(f"Стиль: {prefs['style']}")
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


def smart_reply(user_id: int, text: str, reminder_state: dict = None) -> dict:
    """
    Единая функция: ИИ сам решает, что делать, и возвращает готовую инструкцию.
    
    Возвращает:
    {
      "action": "reply" | "generate_image" | "set_reminder" | "save_reminder" | "cancel_reminder" | "delete_reminder" | "delete_all_reminders" | "list_reminders" | "search_web",
      "reply": "текст для пользователя",
      "prompt": "...",         # для generate_image
      "text": "...",           # для set_reminder
      "time": "HH:MM",
      "date": "YYYY-MM-DD",
      "query": "...",          # для search_web
      "fact": "...",           # для remember (запоминание)
      "reminder_id": 123,      # для delete_reminder
      "delete_all": true
    }
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"action": "reply", "reply": "⚠️ Сервис недоступен. Напиши админу: " + ADMIN_EMAIL}

    client = get_openai_client()
    if not client:
        return {"action": "reply", "reply": "⚠️ Сервис недоступен. Напиши админу: " + ADMIN_EMAIL}

    model = get_model_setting("text_chat") or "deepseek-v4-flash"

    context, history = _get_user_context(user_id)

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M (%A)")
    today_str = now.strftime("%Y-%m-%d")
    tomorrow_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    reminder_context = ""
    if reminder_state:
        reminder_context = f"""
АКТИВНЫЙ ДИАЛОГ НАПОМИНАНИЯ:
Собрано: text={reminder_state.get('text', '')!r}, time={reminder_state.get('time', '')!r}, date={reminder_state.get('date', '')!r}
Последний вопрос: {reminder_state.get('question', '')!r}
"""

    system_prompt = f"""Ты — Vertex AI, умный Telegram-ассистент. Ты САМ решаешь, что делать, и возвращаешь JSON.

СЕЙЧАС: {now_str}
СЕГОДНЯ: {today_str}, ЗАВТРА: {tomorrow_str}

ЧТО ТЫ ЗНАЕШЬ О ПОЛЬЗОВАТЕЛЕ:
{context if context else "(пока ничего)"}
{reminder_context}

Верни ТОЛЬКО JSON такой структуры:
{{
  "action": "одно из действий",
  "reply": "текст, который увидят в чате (только для action=reply)",
  "prompt": "промпт для картинки (только для generate_image)",
  "text": "текст напоминания (для set_reminder)",
  "time": "HH:MM (для set_reminder)",
  "date": "YYYY-MM-DD или today/tomorrow (для set_reminder)",
  "need_clarification": true/false,
  "question": "вопрос, если need_clarification=true",
  "query": "запрос (для search_web)",
  "fact": "факт о пользователе (для remember)",
  "reminder_id": число (для delete_reminder),
  "delete_all": true/false
}}

ДЕЙСТВИЯ:
- reply — обычный ответ пользователю. Используй поле "reply" с готовым текстом.
- generate_image — пользователь просит нарисовать. Поле "prompt".
- set_reminder — установить напоминание. Поля text/time/date. Если чего-то не хватает — need_clarification=true + question.
- cancel_reminder — отменить активный диалог напоминания.
- delete_reminder — удалить напоминание. Поле "text" (что удалить).
- delete_all_reminders — удалить все. delete_all=true.
- list_reminders — показать список.
- search_web — поиск в интернете. Поле "query".
- remember — запомнить факт. Поле "fact".

ПРАВИЛА:
1. Ты — умный ассистент. Если пользователь спрашивает о своём хобби, интересах, имени, предпочтениях — используй данные выше и отвечай в action="reply". Не отправляй в show_help / show_profile.
2. "покажи профиль", "/profile" → action="reply" с текстом профиля (сформируй сам).
3. "помощь", "что ты умеешь" → action="reply" с описанием возможностей.
4. "поменяй моё имя на X", "меня зовут X" → remember с fact="имя пользователя X".
5. "я люблю X", "я увлекаюсь X" → remember с fact.
6. При активном диалоге напоминания — собери недостающие поля через question, либо установи, если всё есть (action="set_reminder").
7. Если невалидное время/дата — не молчи, задай вопрос в question.
8. Если сомневаешься — просто ответь "reply".

Отвечай ТОЛЬКО JSON."""

    messages = [{"role": "system", "content": system_prompt}]

    # История диалога
    for msg in history:
        role = "user" if msg.get("role") == "user" else "assistant"
        messages.append({"role": role, "content": msg.get("text", "")})

    messages.append({"role": "user", "content": text})

    def _try_model(m):
        try:
            resp = client.chat.completions.create(
                model=m,
                messages=messages,
                max_tokens=600,
                temperature=0.3
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

    raw = None
    for m in [model, "gpt-4.1-nano", "gpt-4.1-mini", "deepseek-v4-pro"]:
        raw = _try_model(m)
        if raw:
            break

    if not raw:
        return {"action": "reply", "reply": "😔 Не смог ответить. Попробуй ещё раз или напиши админу: " + ADMIN_EMAIL}

    # Парсим JSON
    json_match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not json_match:
        return {"action": "reply", "reply": raw}

    try:
        data = json.loads(json_match.group())
        logger.info(f"🧠 [{user_id}] smart_reply: {data}")
        return data
    except Exception as e:
        logger.error(f"❌ JSON parse: {e}")
        return {"action": "reply", "reply": raw}


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
