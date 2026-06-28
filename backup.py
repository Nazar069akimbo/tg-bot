import os, base64, logging, shutil
from datetime import datetime, timedelta
import requests

logger = logging.getLogger(__name__)

class GitHubBackup:
    def __init__(self):
        self.token = os.getenv('GITHUB_TOKEN')
        self.repo = os.getenv('GITHUB_BACKUP_REPO')
        self.branch = os.getenv('GITHUB_BACKUP_BRANCH', 'main')
        self.headers = {'Authorization': f'token {self.token}', 'Accept': 'application/vnd.github.v3+json'} if self.token and self.repo else None
    
    def backup_db(self, db_path='data/repsolver.db', reason='auto'):
        if not self.headers: return False
        if not os.path.exists(db_path): return False
        
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        backup_name = f'repsolver_backup_{timestamp}.db'
        shutil.copy2(db_path, backup_name)
        
        with open(backup_name, 'rb') as f:
            content = base64.b64encode(f.read()).decode()
        
        url = f'https://api.github.com/repos/{self.repo}/contents/backups/{backup_name}'
        data = {'message': f'Backup {backup_name}', 'content': content, 'branch': self.branch}
        
        resp = requests.get(url, headers=self.headers)
        if resp.status_code == 200:
            data['sha'] = resp.json()['sha']
        
        resp = requests.put(url, headers=self.headers, json=data)
        os.remove(backup_name)
        
        if resp.status_code in [200, 201]:
            logger.info(f"✅ Бэкап загружен")
            self.cleanup_old_backups()
            return True
        return False
    
    def restore_latest_backup(self, db_path='data/repsolver.db'):
        if not self.headers: return False
        url = f'https://api.github.com/repos/{self.repo}/contents/backups'
        resp = requests.get(url, headers=self.headers)
        if resp.status_code != 200: return False
        
        files = [f for f in resp.json() if f['name'].endswith('.db')]
        if not files: return False
        
        latest = sorted(files, key=lambda x: x['name'], reverse=True)[0]
        resp = requests.get(latest['download_url'])
        if resp.status_code == 200:
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            with open(db_path, 'wb') as f:
                f.write(resp.content)
            logger.info(f"✅ Восстановлен {latest['name']}")
            return True
        return False
    
    def cleanup_old_backups(self, days=7):
        if not self.headers: return
        url = f'https://api.github.com/repos/{self.repo}/contents/backups'
        resp = requests.get(url, headers=self.headers)
        if resp.status_code != 200: return
        
        now = datetime.now()
        for f in resp.json():
            if not f['name'].endswith('.db'): continue
            try:
                date_str = f['name'].replace('repsolver_backup_', '').replace('.db', '')
                if (now - datetime.strptime(date_str, '%Y-%m-%d_%H-%M-%S')) > timedelta(days=days):
                    requests.delete(f'https://api.github.com/repos/{self.repo}/contents/backups/{f["name"]}',
                                  headers=self.headers, json={'message': 'Delete old backup', 'sha': f['sha'], 'branch': self.branch})
                    logger.info(f"🗑️ Удален старый бэкап")
            except: pass
