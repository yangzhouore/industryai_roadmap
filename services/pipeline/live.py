"""Real-source daily pipeline. Missing credentials block publication explicitly."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from .ingest import ingest
from .store import Store


def execute(database, registry='config/sources.yaml', dry_run=False, issue_date=None,
            report_path='artifacts/live-status.json'):
    report = {'startedAt':datetime.now(timezone.utc).isoformat(),'mode':'live',
              'dryRun':dry_run,'published':0}
    store = None
    try:
        report['collection'] = ingest(registry, database, 'live')
        store = Store(database)
        rows = store.execute('''SELECT a.id,a.title,a.canonical_url,a.body_excerpt,a.published_at,
            a.event_at,a.source_timezone,a.raw_metadata,s.name FROM raw_articles a
            JOIN sources s ON s.id=a.source_id WHERE s.source_type<>'fixture'
            ORDER BY a.published_at DESC LIMIT 120''').fetchall()
        articles = []
        for row in rows:
            metadata = row[7] if isinstance(row[7],dict) else json.loads(row[7])
            if metadata.get('synthetic') is not False:
                continue
            articles.append(dict(metadata,id=row[0],title=row[1],url=row[2],excerpt=row[3],
                                 publishedAt=row[4].isoformat(),eventAt=row[5].isoformat() if row[5] else None,
                                 timezone=row[6],name=row[8]))
        report['realArticleCount'] = len(articles)
        candidates = articles[:30]
        report['candidatesConsidered'] = len(candidates)
        if not articles:
            raise RuntimeError('No real source evidence collected; publication blocked')
        day = issue_date or datetime.now(timezone.utc).date().isoformat()
        existing = [i for i in store.published() if i.get('date') == day and i.get('synthetic') is False]
        if existing:
            report.update(status='unchanged',slug=existing[0]['slug'])
        elif not os.getenv('OPENAI_API_KEY','').strip():
            report.update(status='blocked',blocker='OPENAI_API_KEY is absent; AI editorial and translation were not run')
        else:
            from .editorial.live import generate_real_issue
            def retain_draft(candidate):
                path = Path('artifacts/live-draft.json')
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(json.dumps({'draft':candidate,'review':None},ensure_ascii=False,indent=2),encoding='utf-8')
                if not dry_run:
                    store.save_draft(candidate)
            draft,review = generate_real_issue(candidates,day,draft_sink=retain_draft)
            target = Path('artifacts/live-draft.json')
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(json.dumps({'draft':draft,'review':review},ensure_ascii=False,indent=2),encoding='utf-8')
            if dry_run:
                report.update(status='validated-dry-run',draftPath=str(target))
            else:
                report['published'] = int(store.publish(draft,review=review))
                report.update(status='published' if report['published'] else 'unchanged',slug=draft['slug'])
    except Exception as error:
        report.update(status='failed',error=type(error).__name__,message=str(error)[:2000])
    finally:
        report['endedAt'] = datetime.now(timezone.utc).isoformat()
        if store:
            store.log_run('live',report['status'],report)
            store.close()
        target = Path(report_path)
        target.parent.mkdir(parents=True,exist_ok=True)
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(target)
    return report


if __name__ == '__main__':
    from .config import load_project_environment
    load_project_environment()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',default=os.getenv('DATABASE_URL'))
    parser.add_argument('--registry',default='config/sources.yaml')
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--date')
    args=parser.parse_args()
    if not args.database:
        parser.error('DATABASE_URL or --database is required')
    result=execute(args.database,args.registry,args.dry_run,args.date)
    print(json.dumps(result,ensure_ascii=False))
    raise SystemExit(0 if result['status'] in {'published','unchanged','validated-dry-run'} else 1)
