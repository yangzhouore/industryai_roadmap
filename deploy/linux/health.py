"""Read-only private health probe. No provider calls or database writes."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from preflight import database


def main():
    result = {'checkedAt': datetime.now(timezone.utc).isoformat(), 'healthy': False}
    try:
        database(os.getenv('DATABASE_URL'), 'health')
        import psycopg
        with psycopg.connect(os.environ['DATABASE_URL'], connect_timeout=5,
                            options='-c default_transaction_read_only=on', autocommit=True) as db:
            result['databaseReadOnly'] = db.execute('SHOW default_transaction_read_only').fetchone()[0] == 'on'
            result['publishedRealEditions'] = db.execute("SELECT count(*) FROM issues WHERE state='published' AND validated AND content->>'synthetic'='false'").fetchone()[0]
        with urlopen('http://127.0.0.1:3000/en', timeout=10) as response:
            result['webHTTP'] = response.status
            assert response.status == 200 and b'<html' in response.read(1000000)
        root = HERE.parents[1]
        config = json.loads((root/'config/automation.json').read_text(encoding='utf-8'))
        result['paidConfigured'] = config.get('unattendedPaidApproved') is True
        report = Path('/var/lib/industrial-ai/artifacts/daily-status.json')
        if report.is_file():
            daily = json.loads(report.read_text(encoding='utf-8'))
            result['pipelineStatus'] = daily.get('status')
            finished = datetime.fromisoformat(daily['endedAt'].replace('Z', '+00:00'))
            result['reportAgeHours'] = (datetime.now(timezone.utc)-finished).total_seconds()/3600
            result['missedDates'] = daily.get('schedule', {}).get('missedDates', [])
            if result['paidConfigured']:
                assert result['reportAgeHours'] < 27 and not result['missedDates']
                assert result['pipelineStatus'] in {'published', 'unchanged', 'no_evidence', 'no_eligible_news'}
        elif result['paidConfigured']:
            raise ValueError('Missing pipeline report after configured activation')
        else:
            result['pipelineStatus'] = 'disabled'
        result['healthy'] = result['databaseReadOnly']
    except Exception as error:
        # Opaque exception type only: database/provider libraries may echo connection values.
        result.update(error=type(error).__name__)
    print(json.dumps(result))
    return 0 if result['healthy'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
