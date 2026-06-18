import os
import json
import shutil
import logging
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io

logger = logging.getLogger(__name__)

class DriveBackup:
    def __init__(self):
        """Инициализация Google Drive"""
        creds_json = os.getenv('GOOGLE_DRIVE_CREDENTIALS')
        if not creds_json:
            logger.error("❌ GOOGLE_DRIVE_CREDENTIALS не найдены!")
            self.service = None
            self.folder_id = None
            return
        
        try:
            creds_dict = json.loads(creds_json)
            self.creds = service_account.Credentials.from_service_account_info(
                creds_dict,
                scopes=['https://www.googleapis.com/auth/drive.file']
            )
            self.service = build('drive', 'v3', credentials=self.creds)
            self.folder_id = os.getenv('GOOGLE_DRIVE_FOLDER_ID')
            if self.folder_id:
                logger.info("✅ Google Drive инициализирован")
            else:
                logger.error("❌ GOOGLE_DRIVE_FOLDER_ID не найден!")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Google Drive: {e}")
            self.service = None
            self.folder_id = None
    
    def backup_db(self, db_path='data/repsolver.db'):
        """Бэкап БД в Google Drive"""
        if not self.service:
            logger.warning("⚠️ Google Drive не инициализирован")
            return False
        
        try:
            if not os.path.exists(db_path):
                logger.warning(f"⚠️ Файл {db_path} не найден")
                return False
            
            # Создаем файл бэкапа с датой
            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            backup_name = f'repsolver_backup_{timestamp}.db'
            
            # Копируем БД
            shutil.copy2(db_path, backup_name)
            logger.info(f"📦 Создан локальный бэкап: {backup_name}")
            
            # Загружаем в Google Drive
            file_metadata = {
                'name': backup_name,
                'parents': [self.folder_id]
            }
            media = MediaFileUpload(backup_name, mimetype='application/x-sqlite3')
            
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            # Удаляем временный файл
            os.remove(backup_name)
            
            logger.info(f"✅ Бэкап загружен в Google Drive: {backup_name}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка бэкапа: {e}")
            return False
    
    def restore_latest_backup(self, db_path='data/repsolver.db'):
        """Восстанавливает последний бэкап"""
        if not self.service:
            logger.warning("⚠️ Google Drive не инициализирован")
            return False
        
        try:
            # Ищем последний бэкап
            results = self.service.files().list(
                q=f"'{self.folder_id}' in parents and name contains 'repsolver_backup'",
                orderBy='createdTime desc',
                pageSize=1,
                fields='files(id, name, createdTime)'
            ).execute()
            
            files = results.get('files', [])
            if not files:
                logger.info("ℹ️ Нет бэкапов для восстановления")
                return False
            
            file = files[0]
            logger.info(f"📥 Восстановление из: {file['name']}")
            
            # Создаем папку data если её нет
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            
            # Скачиваем файл
            request = self.service.files().get_media(fileId=file['id'])
            fh = io.FileIO(db_path, 'wb')
            downloader = MediaIoBaseDownload(fh, request)
            
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            
            fh.close()
            logger.info(f"✅ БД восстановлена из {file['name']}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка восстановления: {e}")
            return False
    
    def cleanup_old_backups(self, keep=10):
        """Удаляет старые бэкапы"""
        if not self.service:
            return
        
        try:
            results = self.service.files().list(
                q=f"'{self.folder_id}' in parents and name contains 'repsolver_backup'",
                orderBy='createdTime desc',
                fields='files(id, name)'
            ).execute()
            
            files = results.get('files', [])
            if len(files) > keep:
                for file in files[keep:]:
                    self.service.files().delete(fileId=file['id']).execute()
                    logger.info(f"🗑️ Удален старый бэкап: {file['name']}")
        except Exception as e:
            logger.error(f"❌ Ошибка очистки: {e}")
