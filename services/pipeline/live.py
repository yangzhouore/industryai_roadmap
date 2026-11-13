"""Compatibility entrypoint for the budgeted daily runner; defaults to no paid calls."""
import json
from pathlib import Path
from .daily import configuration, execute as daily_execute, main


def execute(database, registry='config/sources.yaml', dry_run=True, issue_date=None,
            report_path='artifacts/live-status.json', *, allow_paid=False, resume=False):
    config = configuration()
    config['registry'] = registry
    result = daily_execute(database, day=issue_date, dry_run=dry_run or not allow_paid,
                           resume=resume, allow_paid=allow_paid, config=config)
    target = Path(report_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    return result


if __name__ == '__main__':
    raise SystemExit(main())
