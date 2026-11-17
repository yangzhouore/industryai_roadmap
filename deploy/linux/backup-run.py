"""Call the audited encrypted off-host backup CLI using protected service environment."""
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from preflight import check


def main():
    try:
        check('backup')
        recipient = os.environ['BACKUP_AGE_RECIPIENT']
        destination = os.environ['BACKUP_DESTINATION']
        if not recipient.startswith('age1') or not destination.startswith('rclone:'):
            raise ValueError('An approved encryption recipient and off-host destination are required')
        credential_file = Path(os.environ['RCLONE_CONFIG'])
        if not credential_file.is_file() or credential_file.stat().st_mode & 0o077:
            raise ValueError('Rclone configuration must allow owner access only')
        config = json.loads(Path('config/automation.json').read_text(encoding='utf-8'))
        legacy = Path('/var/lib/industrial-ai/artifacts/mvp3/budget.json')
        current_month = datetime.now(ZoneInfo('Europe/Berlin')).strftime('%Y-%m')
        if current_month == config.get('legacyBudgetMonth') and not os.access(legacy, os.R_OK):
            raise ValueError('Required November legacy state is missing or unreadable')
        extra = ['--state-file', str(legacy)] if os.access(legacy, os.R_OK) else []
        result = subprocess.run([sys.executable, 'packages/db/recovery.py', 'backup',
            '--database-env','DATABASE_URL','--recipient-env','BACKUP_AGE_RECIPIENT',
            '--destination',destination,'--state-dir','/var/lib/industrial-ai/backups',*extra],
            capture_output=True, text=True, check=False)
        if result.returncode:
            raise ValueError('Encrypted off-host backup failed')
        data = json.loads(result.stdout)
        print(json.dumps({'backupId':data['backupId'], 'realArticles':data['realArticles'],
            'publishedDates':data['publishedDates'], 'revisionCount':data['revisionCount'], 'encrypted':data['encrypted']}))
        return 0
    except Exception:
        print(json.dumps({'status':'failed','error':'Backup service refused or failed; credentials withheld'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
