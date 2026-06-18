import os
import pickle
import shutil
import logging
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive.file']
TOKEN_FILE = 'token.pickle'
CREDS_FILE = 'credentials.json'

class DriveBackup:
    def __init__(self):
        """Инициализация Google Drive через OAuth"""
        self.service = None
        self.folder_id = os.getenv('GOOGLE_DRIVE_FOLDER_ID')
        
        # Проверяем, есть ли файл с ключами
        if not os.path.exists(CREDS_FILE):
            logger.error(f"❌ Файл {CREDS_FILE} не найден в папке проекта!")
            return
        
        try:
            creds = None
            
            # Проверяем, есть ли сохраненный токен
            if os.path.exists(TOKEN_FILE):
                with open(TOKEN_FILE, 'rb') as token:
                    creds = pickle.load(token)
                logger.info("📂 Найден сохраненный токен")
            
            # Если токен невалидный - обновляем
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                logger.info("🔄 Токен обновлен")
            elif not creds:
                # Если нет токена - просим авторизоваться
                logger.info("🔐 Требуется авторизация в Google...")
                flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
                creds = flow.run_local_server(port=8080)
                logger.info("✅ Авторизация прошла успешно")
            
            # Сохраняем токен для следующего раза
            with open(TOKEN_FILE, 'wb') as token:
                pickle.dump(creds, token)
            
            self.service = build('drive', 'v3', credentials=creds)
            logger.info("✅ Google Drive инициализирован (OAuth)")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации: {e}")
            self.service = None
    
    def backup_db(self, db_path='data/repsolver.db'):
        """Бэкап БД в Google Drive"""
        if not self.service:
            logger.warning("⚠️ Google Drive не инициализирован")
            return False
        
        if not self.folder_id:
            logger.error("❌ GOOGLE_DRIVE_FOLDER_ID не найден!")
            return False
        
        try:
            if not os.path.exists(db_path):
                logger.warning(f"⚠️ Файл {db_path} не найден")
                return False
            
            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            backup_name = f'repsolver_backup_{timestamp}.db'
            shutil.copy2(db_path, backup_name)
            logger.info(f"📦 Создан локальный бэкап: {backup_name}")
            
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
        
        if not self.folder_id:
            logger.error("❌ GOOGLE_DRIVE_FOLDER_ID не найден!")
            return False
        
        try:
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
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            
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
