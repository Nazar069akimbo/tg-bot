import os
import shutil
import logging
import base64
from datetime import datetime
import requests

logger = logging.getLogger(__name__)


class GitHubBackup:
    def __init__(self):
        self.token = os.getenv('GITHUB_TOKEN')
        self.repo = os.getenv('GITHUB_BACKUP_REPO')
        self.branch = os.getenv('GITHUB_BACKUP_BRANCH', 'main')

        if not self.token:
            logger.error("❌ GITHUB_TOKEN не найден!")
            return
        if not self.repo:
            logger.error("❌ GITHUB_BACKUP_REPO не найден!")
            return

        self.headers = {
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        logger.info(f"✅ GitHub бэкап инициализирован для {self.repo}")

    # ===== БД =====
    def backup_db(self, db_path='data/repsolver.db', reason='автоматический'):
        try:
            if not os.path.exists(db_path):
                logger.warning(f"⚠️ Файл {db_path} не найден")
                return False

            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            backup_name = f'repsolver_backup_{timestamp}.db'
            shutil.copy2(db_path, backup_name)

            with open(backup_name, 'rb') as f:
                content = base64.b64encode(f.read()).decode('utf-8')

            file_path = f'backups/db/{backup_name}'
            ok = self._upload_file(file_path, content, f'Бэкап БД {backup_name} ({reason})')
            os.remove(backup_name)

            if ok:
                self._cleanup_old('backups/db', keep=10)
            return ok

        except Exception as e:
            logger.error(f"❌ Ошибка бэкапа БД: {e}")
            return False

    # ===== ПОЛЬЗОВАТЕЛИ =====
    def backup_users(self, reason='автоматический'):
        try:
            base = 'data/users'
            if not os.path.exists(base):
                logger.info("ℹ️ Папка data/users пуста")
                return True

            uploaded = 0
            for root, dirs, files in os.walk(base):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, base).replace('\\', '/')
                    repo_path = f'backups/users/{rel_path}'

                    try:
                        with open(full_path, 'rb') as f:
                            content = base64.b64encode(f.read()).decode('utf-8')
                        if self._upload_file(repo_path, content, f'user: {rel_path} ({reason})'):
                            uploaded += 1
                    except Exception as e:
                        logger.warning(f"⚠️ Не залит {rel_path}: {e}")

            logger.info(f"✅ Бэкап пользователей: {uploaded} файлов")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка бэкапа пользователей: {e}")
            return False

    def backup_all(self, reason='автоматический'):
        logger.info(f"🔄 Полный бэкап ({reason})...")
        db_ok = self.backup_db(reason=reason)
        users_ok = self.backup_users(reason=reason)
        if db_ok and users_ok:
            logger.info("✅ Полный бэкап завершён")
            return True
        logger.warning("⚠️ Бэкап завершён с ошибками")
        return False

    # ===== ВОССТАНОВЛЕНИЕ =====
    def restore_latest_backup(self, db_path='data/repsolver.db'):
        try:
            url = f'https://api.github.com/repos/{self.repo}/contents/backups/db'
            response = requests.get(url, headers=self.headers)
            if response.status_code != 200:
                logger.info("ℹ️ Нет бэкапов")
                return False

            files = response.json()
            db_files = [f for f in files if f['name'].endswith('.db')]
            if not db_files:
                return False

            db_files.sort(key=lambda x: x['name'], reverse=True)
            latest = db_files[0]
            logger.info(f"📥 Восстановление из: {latest['name']}")

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
    def _upload_file(self, repo_path, content_b64, message):
        url = f'https://api.github.com/repos/{self.repo}/contents/{repo_path}'
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
            logger.error(f"❌ Ошибка загрузки {repo_path}: {response.text[:200]}")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка upload {repo_path}: {e}")
            return False

    def _cleanup_old(self, folder_path, keep=10):
        try:
            url = f'https://api.github.com/repos/{self.repo}/contents/{folder_path}'
            response = requests.get(url, headers=self.headers)
            if response.status_code != 200:
                return
            files = response.json()
            db_files = [f for f in files if f['name'].endswith('.db')]
            db_files.sort(key=lambda x: x['name'], reverse=True)
            if len(db_files) <= keep:
                return
            for file in db_files[keep:]:
                delete_url = f'https://api.github.com/repos/{self.repo}/contents/{folder_path}/{file["name"]}'
                data = {'message': f'Удаление {file["name"]}', 'sha': file['sha'], 'branch': self.branch}
                requests.delete(delete_url, headers=self.headers, json=data)
        except Exception as e:
            logger.warning(f"⚠️ Ошибка очистки: {e}")
