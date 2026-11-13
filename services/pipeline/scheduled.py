"""Single scheduled validation run with machine-readable monitoring output."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from .cli import run


def execute(input_path=None, report_path='artifacts/pipeline-status.json'):
    report = {'startedAt': datetime.now(timezone.utc).isoformat(), 'mode': 'dry-run'}
    try:
        args = ['--mode', 'dry-run']
        if input_path:
            args += ['--input', str(input_path)]
        report['stats'] = run(args)
        report['status'] = 'success'
    except Exception as error:
        report.update(status='failed', error=type(error).__name__, message=str(error)[:2000])
    report['endedAt'] = datetime.now(timezone.utc).isoformat()
    target = Path(report_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(target)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input')
    parser.add_argument('--report', default='artifacts/pipeline-status.json')
    arguments = parser.parse_args()
    result = execute(arguments.input, arguments.report)
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result['status'] == 'success' else 1)
