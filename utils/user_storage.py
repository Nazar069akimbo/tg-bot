import os
import json
import re
import time
import logging
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_DIR = "data/users"
_last_backup_time = {"users": 0}
BACKUP_INTERVAL = 300


def _safe_name(name: str) -> str:
    """Превращает имя в безопасное для файловой системы."""
    if not name:
        return ""
    # Убираем всё, кроме букв, цифр, пробелов, дефисов и подчёркиваний
    safe = re.sub(r'[^\w\s\-]', '', name, flags=re.UNICODE).strip()
    safe = safe.replace(" ", "_")
    return safe[:50]


def get_user_dir(user_id: int) -> str:
    """
    Возвращает путь к папке пользователя.
    Если знаем имя — используем его, иначе ID.
    """
    from utils.user_storage import load_profile  # локальный импорт
    folder = None
    try:
        profile = load_profile(user_id)
        name = profile.get("name")
        if name:
            safe = _safe_name(name)
            if safe:
                folder = safe
    except Exception:
        pass

    if not folder:
        folder = str(user_id)

    # Проверяем, нет ли коллизии: если папка с таким именем принадлежит другому ID
    base = os.path.join(BASE_DIR, folder)
    id_file = os.path.join(base, "_id.txt")
    if os.path.exists(id_file):
        try:
            with open(id_file, "r", encoding="utf-8") as f:
                owner = f.read().strip()
            if owner != str(user_id):
                # Коллизия — добавляем ID
                folder = f"{folder}_{user_id}"
        except Exception:
            pass

    path = os.path.join(BASE_DIR, folder)
    os.makedirs(path, exist_ok=True)
    os.makedirs(os.path.join(path, "images"), exist_ok=True)

    # Пишем ID-файл, чтобы знать владельца
    try:
        with open(os.path.join(path, "_id.txt"), "w", encoding="utf-8") as f:
            f.write(str(user_id))
    except Exception:
        pass

    return path


def _profile_path(user_id: int) -> str:
    return os.path.join(get_user_dir(user_id), "profile.json")


def _history_path(user_id: int) -> str:
    return os.path.join(get_user_dir(user_id), "history.json")


def _meta_path(user_id: int) -> str:
    return os.path.join(get_user_dir(user_id), "meta.json")


def _backup_users(force: bool = False):
    now = time.time()
    if not force and now - _last_backup_time["users"] < BACKUP_INTERVAL:
        return
    _last_backup_time["users"] = now

    def _run():
        try:
            from backup import GitHubBackup
            GitHubBackup().backup_users(reason='после изменения')
        except Exception as e:
            logger.warning(f"⚠️ Ошибка бэкапа: {e}")

    threading.Thread(target=_run, daemon=True).start()


# ===== PROFILE =====
def load_profile(user_id: int) -> dict:
    # Ищем папку: сначала по ID (старая), потом по имени
    path_id = os.path.join(BASE_DIR, str(user_id), "profile.json")
    if os.path.exists(path_id):
        try:
            with open(path_id, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    path = _profile_path(user_id)
    if not os.path.exists(path):
        return {
            "user_id": user_id,
            "name": None,
            "preferences": {
                "style": None,
                "colors": None,
                "hobbies": [],
                "favorite_topics": [],
                "facts": []
            },
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("preferences", {})
            data["preferences"].setdefault("facts", [])
            return data
    except Exception as e:
        logger.error(f"❌ profile.json [{user_id}]: {e}")
        return {}


def save_profile(user_id: int, data: dict):
    data["updated_at"] = datetime.now().isoformat()
    try:
        with open(_profile_path(user_id), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        _backup_users()
    except Exception as e:
        logger.error(f"❌ save profile [{user_id}]: {e}")


def set_user_name(user_id: int, name: str):
    # Загружаем СТАРЫЙ профиль (по ID, если есть)
    profile = None
    old_path = os.path.join(BASE_DIR, str(user_id), "profile.json")
    if os.path.exists(old_path):
        try:
            with open(old_path, "r", encoding="utf-8") as f:
                profile = json.load(f)
        except Exception:
            pass
    if not profile:
        profile = load_profile(user_id)

    profile["name"] = name

    # Если папка старая (по ID) — переносим в новую (по имени)
    old_dir = os.path.join(BASE_DIR, str(user_id))
    new_dir = os.path.join(BASE_DIR, _safe_name(name) or str(user_id))
    if old_dir != new_dir and os.path.exists(old_dir):
        try:
            import shutil
            if os.path.exists(new_dir):
                shutil.rmtree(new_dir)
            shutil.move(old_dir, new_dir)
            logger.info(f"📁 [{user_id}] папка переименована: {old_dir} → {new_dir}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось переименовать папку: {e}")

    # Сохраняем в новой папке
    try:
        with open(_profile_path(user_id), "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        _backup_users()
    except Exception as e:
        logger.error(f"❌ set_user_name [{user_id}]: {e}")


def add_fact(user_id: int, fact: str):
    profile = load_profile(user_id)
    facts = profile.setdefault("preferences", {}).setdefault("facts", [])
    if fact not in facts:
        facts.append(fact)
        if len(facts) > 50:
            profile["preferences"]["facts"] = facts[-50:]
    save_profile(user_id, profile)
    logger.info(f"🧠 [{user_id}] факт: {fact}")


# ===== HISTORY =====
def load_history(user_id: int) -> list:
    path = _history_path(user_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def append_history(user_id: int, role: str, text: str):
    history = load_history(user_id)
    history.append({"role": role, "text": text, "timestamp": datetime.now().isoformat()})
    if len(history) > 100:
        history = history[-100:]
    try:
        with open(_history_path(user_id), "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        _backup_users()
    except Exception as e:
        logger.error(f"❌ append_history [{user_id}]: {e}")


def get_recent_history(user_id: int, limit: int = 20) -> list:
    history = load_history(user_id)
    return history[-limit:] if len(history) > limit else history


# ===== META =====
def load_meta(user_id: int) -> dict:
    path = _meta_path(user_id)
    if not os.path.exists(path):
        return {"user_id": user_id, "images_count": 0, "tokens_spent": 0,
                "last_topics": [], "created_at": datetime.now().isoformat()}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"user_id": user_id, "images_count": 0, "tokens_spent": 0, "last_topics": []}


def update_meta(user_id: int, **kwargs):
    meta = load_meta(user_id)
    for k, v in kwargs.items():
        if k == "last_topics" and isinstance(v, list):
            topics = meta.get("last_topics", [])
            topics.extend(v)
            meta["last_topics"] = topics[-10:]
        else:
            meta[k] = v
    try:
        with open(_meta_path(user_id), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"❌ update_meta [{user_id}]: {e}")


# ===== IMAGES =====
def save_user_image(user_id: int, image_id: int, image_bytes: bytes) -> str:
    path = os.path.join(get_user_dir(user_id), "images", f"{image_id}.png")
    try:
        with open(path, "wb") as f:
            f.write(image_bytes)
        meta = load_meta(user_id)
        meta["images_count"] = meta.get("images_count", 0) + 1
        with open(_meta_path(user_id), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        _backup_users()
        return path
    except Exception as e:
        logger.error(f"❌ save image [{user_id}]: {e}")
        return ""


# ===== CLEAR =====
def clear_memory(user_id: int):
    for path in (_history_path(user_id), _profile_path(user_id)):
        if os.path.exists(path):
            os.remove(path)
    logger.info(f"🧹 [{user_id}] память очищена")


# Совместимость
def update_profile_field(user_id: int, key: str, value):
    if key == "name":
        set_user_name(user_id, value)
    else:
        add_fact(user_id, f"пользователь: {key} = {value}")
