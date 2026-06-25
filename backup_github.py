import os
import shutil
import logging
import base64
from datetime import datetime, timedelta
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
    
    def backup_db(self, db_path='data/repsolver.db', reason='автоматический'):
        try:
            if not os.path.exists(db_path):
                logger.warning(f"⚠️ Файл {db_path} не найден")
                return False
            
            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            backup_name = f'repsolver_backup_{timestamp}.db'
            shutil.copy2(db_path, backup_name)
            logger.info(f"📦 Создан бэкап ({reason}): {backup_name}")
            
            with open(backup_name, 'rb') as f:
                content = base64.b64encode(f.read()).decode('utf-8')
            
            file_path = f'backups/{backup_name}'
            url = f'https://api.github.com/repos/{self.repo}/contents/{file_path}'
            
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                sha = response.json()['sha']
                data = {
                    'message': f'Обновление бэкапа {backup_name} ({reason})',
                    'content': content,
                    'sha': sha,
                    'branch': self.branch
                }
            else:
                data = {
                    'message': f'Добавлен бэкап {backup_name} ({reason})',
                    'content': content,
                    'branch': self.branch
                }
            
            response = requests.put(url, headers=self.headers, json=data)
            
            if response.status_code in [200, 201]:
                logger.info(f"✅ Бэкап загружен в GitHub ({reason}): {file_path}")
                os.remove(backup_name)
                self.cleanup_old_backups(days=7)
                return True
            else:
                logger.error(f"❌ Ошибка загрузки: {response.text}")
                os.remove(backup_name)
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка бэкапа: {e}")
            return False
    
    def restore_latest_backup(self, db_path='data/repsolver.db'):
        try:
            url = f'https://api.github.com/repos/{self.repo}/contents/backups'
            response = requests.get(url, headers=self.headers)
            
            if response.status_code != 200:
                logger.info("ℹ️ Нет бэкапов для восстановления")
                return False
            
            files = response.json()
            db_files = [f for f in files if f['name'].endswith('.db')]
            
            if not db_files:
                logger.info("ℹ️ Нет .db файлов для восстановления")
                return False
            
            db_files.sort(key=lambda x: x['name'], reverse=True)
            latest = db_files[0]
            
            logger.info(f"📥 Восстановление из: {latest['name']}")
            
            download_url = latest['download_url']
            response = requests.get(download_url)
            
            if response.status_code == 200:
                os.makedirs(os.path.dirname(db_path), exist_ok=True)
                with open(db_path, 'wb') as f:
                    f.write(response.content)
                logger.info(f"✅ БД восстановлена из {latest['name']}")
                return True
            else:
                logger.error(f"❌ Ошибка скачивания: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка восстановления: {e}")
            return False
    
    def cleanup_old_backups(self, days=7):
        try:
            url = f'https://api.github.com/repos/{self.repo}/contents/backups'
            response = requests.get(url, headers=self.headers)
            
            if response.status_code != 200:
                return
            
            files = response.json()
            db_files = [f for f in files if f['name'].endswith('.db')]
            
            now = datetime.now()
            deleted_count = 0
            
            for file in db_files:
                try:
                    date_str = file['name'].replace('repsolver_backup_', '').replace('.db', '')
                    file_date = datetime.strptime(date_str, '%Y-%m-%d_%H-%M-%S')
                    
                    if (now - file_date) > timedelta(days=days):
                        delete_url = f'https://api.github.com/repos/{self.repo}/contents/backups/{file["name"]}'
                        data = {
                            'message': f'Удаление старого бэкапа {file["name"]}',
                            'sha': file['sha'],
                            'branch': self.branch
                        }
                        response = requests.delete(delete_url, headers=self.headers, json=data)
                        if response.status_code == 200:
                            logger.info(f"🗑️ Удален старый бэкап: {file['name']}")
                            deleted_count += 1
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось обработать файл {file['name']}: {e}")
            
            if deleted_count > 0:
                logger.info(f"✅ Удалено {deleted_count} старых бэкапов")
            
        except Exception as e:
            logger.error(f"❌ Ошибка очистки: {e}")
