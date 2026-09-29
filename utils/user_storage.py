import os
import json
import time
import logging
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_DIR = "data/users"
_last_backup_time = {"users": 0}
BACKUP_INTERVAL = 300  # 5 минут


def get_user_dir(user_id: int) -> str:
    path = os.path.join(BASE_DIR, str(user_id))
    os.makedirs(path, exist_ok=True)
    os.makedirs(os.path.join(path, "images"), exist_ok=True)
    return path


def _profile_path(user_id: int) -> str:
    return os.path.join(get_user_dir(user_id), "profile.json")


def _history_path(user_id: int) -> str:
    return os.path.join(get_user_dir(user_id), "history.json")


def _meta_path(user_id: int) -> str:
    return os.path.join(get_user_dir(user_id), "meta.json")


def _backup_users(force: bool = False):
    """Бэкап пользователей в GitHub, не чаще раза в 5 минут."""
    now = time.time()
    if not force and now - _last_backup_time["users"] < BACKUP_INTERVAL:
        return
    _last_backup_time["users"] = now

    def _run():
        try:
            from backup import GitHubBackup
            GitHubBackup().backup_users(reason='после изменения')
        except Exception as e:
            logger.warning(f"⚠️ Ошибка бэкапа пользователей: {e}")

    threading.Thread(target=_run, daemon=True).start()


# ===== PROFILE =====
def load_profile(user_id: int) -> dict:
    path = _profile_path(user_id)
    if not os.path.exists(path):
        return {
            "user_id": user_id,
            "name": None,
            "preferences": {"style": None, "colors": None, "hobbies": [], "favorite_topics": []},
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
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


def update_profile_field(user_id: int, key: str, value):
    profile = load_profile(user_id)
    if key == "name":
        profile["name"] = value
    else:
        profile.setdefault("preferences", {})
        if isinstance(profile["preferences"].get(key), list):
            if value not in profile["preferences"][key]:
                profile["preferences"][key].append(value)
        else:
            profile["preferences"][key] = value
    save_profile(user_id, profile)
    logger.info(f"🧠 [{user_id}] profile: {key} = {value}")


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
        logger.info(f"💾 [{user_id}] image: {path}")
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
    logger.info(f"🧹 [{user_id}] память очищена (картинки сохранены)")
