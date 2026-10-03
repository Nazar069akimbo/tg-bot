import os
import shutil
import logging
import base64
import time
import threading
from datetime import datetime
import requests

logger = logging.getLogger(__name__)


class GitHubBackup:
    def __init__(self):
        self.token = os.getenv('GITHUB_TOKEN')
        self.repo_db = os.getenv('GITHUB_BACKUP_REPO')
        self.repo_users = os.getenv('GITHUB_USERS_REPO')
        self.branch = os.getenv('GITHUB_BACKUP_BRANCH', 'main')

        if not self.token:
            logger.error("❌ GITHUB_TOKEN не найден!")
        if not self.repo_db:
            logger.error("❌ GITHUB_BACKUP_REPO не найден!")
        if not self.repo_users:
            logger.error("❌ GITHUB_USERS_REPO не найден!")

        self.headers = {
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        logger.info(f"✅ Backup: БД → {self.repo_db}, юзеры → {self.repo_users}")

    # ===== БД (раз в 30 минут) =====
    def backup_db(self, db_path='data/repsolver.db', reason='автоматический'):
        try:
            if not self.repo_db or not os.path.exists(db_path):
                return False

            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            backup_name = f'repsolver_backup_{timestamp}.db'
            shutil.copy2(db_path, backup_name)

            with open(backup_name, 'rb') as f:
                content = base64.b64encode(f.read()).decode('utf-8')

            file_path = f'db/{backup_name}'
            ok = self._upload_file(self.repo_db, file_path, content, f'БД {backup_name} ({reason})')
            os.remove(backup_name)

            if ok:
                self._cleanup_old(self.repo_db, 'db', keep=20)
            return ok

        except Exception as e:
            logger.error(f"❌ Ошибка бэкапа БД: {e}")
            return False

    # ===== ПОЛЬЗОВАТЕЛИ (после каждого действия) =====
    def backup_users(self, reason='изменение'):
        try:
            if not self.repo_users:
                return False

            base = 'data/users'
            if not os.path.exists(base):
                return True

            uploaded = 0
            for root, dirs, files in os.walk(base):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, base).replace('\\', '/')
                    repo_path = f'users/{rel_path}'

                    try:
                        with open(full_path, 'rb') as f:
                            content = base64.b64encode(f.read()).decode('utf-8')
                        if self._upload_file(self.repo_users, repo_path, content, f'{rel_path} ({reason})'):
                            uploaded += 1
                    except Exception as e:
                        logger.warning(f"⚠️ Не залит {rel_path}: {e}")

            if uploaded > 0:
                logger.info(f"✅ Бэкап пользователей: {uploaded} файлов")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка бэкапа пользователей: {e}")
            return False

    def backup_all(self, reason='полный'):
        logger.info(f"🔄 Полный бэкап ({reason})...")
        db_ok = self.backup_db(reason=reason)
        users_ok = self.backup_users(reason=reason)
        return db_ok and users_ok

    # ===== ВОССТАНОВЛЕНИЕ =====
    def restore_latest_backup(self, db_path='data/repsolver.db'):
        try:
            if not self.repo_db:
                return False
            url = f'https://api.github.com/repos/{self.repo_db}/contents/db'
            response = requests.get(url, headers=self.headers)
            if response.status_code != 200:
                return False

            files = response.json()
            db_files = [f for f in files if f['name'].endswith('.db')]
            if not db_files:
                return False

            db_files.sort(key=lambda x: x['name'], reverse=True)
            latest = db_files[0]
            logger.info(f"📥 Восстановление БД из: {latest['name']}")

            response = requests.get(latest['download_url'])
            if response.status_code == 200:
                os.makedirs(os.path.dirname(db_path), exist_ok=True)
                with open(db_path, 'wb') as f:
                    f.write(response.content)
                logger.info(f"✅ БД восстановлена из {latest['name']}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка восстановления: {e}")
            return False

    # ===== ВСПОМОГАТЕЛЬНЫЕ =====
    def _upload_file(self, repo, repo_path, content_b64, message):
        url = f'https://api.github.com/repos/{repo}/contents/{repo_path}'
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                sha = response.json()['sha']
                data = {'message': message, 'content': content_b64, 'sha': sha, 'branch': self.branch}
            else:
                data = {'message': message, 'content': content_b64, 'branch': self.branch}

            response = requests.put(url, headers=self.headers, json=data)
            if response.status_code in (200, 201):
                return True
            logger.error(f"❌ Загрузка {repo_path} в {repo}: {response.text[:200]}")
            return False
        except Exception as e:
            logger.error(f"❌ upload {repo_path}: {e}")
            return False

    def _cleanup_old(self, repo, folder_path, keep=20):
        try:
            url = f'https://api.github.com/repos/{repo}/contents/{folder_path}'
            response = requests.get(url, headers=self.headers)
            if response.status_code != 200:
                return
            files = response.json()
            db_files = [f for f in files if f['name'].endswith('.db')]
            db_files.sort(key=lambda x: x['name'], reverse=True)
            if len(db_files) <= keep:
                return
            for file in db_files[keep:]:
                delete_url = f'https://api.github.com/repos/{repo}/contents/{folder_path}/{file["name"]}'
                data = {'message': f'Удаление {file["name"]}', 'sha': file['sha'], 'branch': self.branch}
                requests.delete(delete_url, headers=self.headers, json=data)
        except Exception as e:
            logger.warning(f"⚠️ Очистка: {e}")


# ===== АВТОБЭКАП ПОЛЬЗОВАТЕЛЕЙ С ЗАДЕРЖКОЙ =====
_users_backup_timer = None
_users_backup_lock = threading.Lock()


def schedule_users_backup(delay=5):
    """Запускает бэкап пользователей через delay секунд (батчинг)."""
    global _users_backup_timer
    with _users_backup_lock:
        if _users_backup_timer is not None:
            _users_backup_timer.cancel()
        _users_backup_timer = threading.Timer(delay, _do_users_backup)
        _users_backup_timer.daemon = True
        _users_backup_timer.start()


def _do_users_backup():
    global _users_backup_timer
    try:
        GitHubBackup().backup_users(reason='изменение')
    except Exception as e:
        logger.warning(f"⚠️ Бэкап пользователей: {e}")
    with _users_backup_lock:
        _users_backup_timer = None
