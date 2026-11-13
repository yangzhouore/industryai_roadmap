"""Daily automation: explicit paid authorization, durable resume, atomic publication."""
import argparse
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import time

from packages.db.automation import AutomationStore
from .config import load_project_environment
from .editorial.provider import OpenAIProvider, ProviderError, StructuredResult
from .ingest import ingest
from .monthly_budget import MonthlyBudget, BudgetExceeded
from .reporting import redacted
from .schedule import (AlreadyRunning, aware_now, latest_due, missed_dates,
                       next_slot, run_lock, slot)
from .store import Store
from .verification.temporal import day_bounds, publication_time

ROOT = Path(__file__).resolve().parents[2]
SUCCESS = {'published', 'unchanged', 'no_eligible_news', 'no_evidence'}


def configuration(path=None):
    value = json.loads(Path(path or ROOT/'config/automation.json').read_text(encoding='utf-8'))
    if value['timezone'] != 'Europe/Berlin' or value['publicationTime'] != '07:00':
        raise ValueError('Supported schedule is 07:00 Europe/Berlin')
    if not 0 < value['monthlyBudgetUSD'] <= 2:
        raise ValueError('Monthly application budget cannot exceed USD 2')
    date.fromisoformat(value['startDate'])
    return value


def _json(value):
    return value if isinstance(value, (dict, list)) else json.loads(value)


def cache_get(store, key):
    row = store.execute('SELECT content FROM automation_cache WHERE cache_key=?', (key,)).fetchone()
    return _json(row[0]) if row else None


def cache_put(store, key, content):
    store.execute('INSERT INTO automation_cache(cache_key,content,created_at) VALUES(?,?,?) ON CONFLICT DO NOTHING',
                  (key, store.json_value(content), datetime.now(timezone.utc).isoformat()))


class CachedProvider:
    """Only completed structured stage results are reused; reviews are sealed anew."""
    def __init__(self, provider, store, day, resume):
        self.provider, self.store, self.day, self.resume = provider, store, day, resume
        self.reused = 0
        self.usage = provider.usage
        self.last_key = None

    def complete_json(self, stage, schema, payload, instructions):
        model = {'classify': self.provider.classification_model,
                 'generate': self.provider.model, 'verify': self.provider.verification_model}[stage]
        material = {'version': 'daily-v1', 'date': self.day, 'stage': stage, 'schema': schema,
                    'payload': payload, 'instructions': instructions, 'model': model,
                    'reasoning': self.provider.reasoning_effort}
        key = 'response:' + sha256(json.dumps(material, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        self.last_key = key
        cached = cache_get(self.store, key) if self.resume else None
        if cached and not cached.get('invalidated'):
            self.reused += 1
            return StructuredResult(deepcopy(cached['data']), cached['responseId'], cached['model'], None)
        result = self.provider.complete_json(stage, schema, payload, instructions)
        from pydantic import ValidationError
        from .editorial.live_schema import Classified, Generated, FactCheck
        try:
            {'classify': Classified, 'generate': Generated, 'verify': FactCheck}[stage].model_validate(result.data)
        except ValidationError:
            raise ProviderError(stage + ': output failed strict local schema validation') from None
        # A rejected attempt can be replaced in the resume cache; its cost ledger is immutable.
        self.store.execute('''INSERT INTO automation_cache(cache_key,content,created_at) VALUES(?,?,?)
            ON CONFLICT(cache_key) DO UPDATE SET content=excluded.content''',
            (key, self.store.json_value({'data': result.data, 'responseId': result.response_id,
                                        'model': result.model}), datetime.now(timezone.utc).isoformat()))
        return result

    def invalidate_last(self):
        if self.last_key:
            self.store.execute('UPDATE automation_cache SET content=? WHERE cache_key=?',
                               (self.store.json_value({'invalidated': True}), self.last_key))


def article_candidates(store, day):
    evidence_day = (date.fromisoformat(day)-timedelta(days=1)).isoformat()
    begin, end = day_bounds(evidence_day)
    articles = []
    rows = store.execute('''SELECT a.id,a.title,a.canonical_url,a.body_excerpt,a.published_at,
        a.event_at,a.source_timezone,a.raw_metadata,s.name FROM raw_articles a
        JOIN sources s ON s.id=a.source_id ORDER BY a.published_at,a.id''').fetchall()
    for row in rows:
        meta = _json(row[7])
        if meta.get('synthetic') is not False:
            continue
        published = row[4].isoformat() if isinstance(row[4], datetime) else row[4]
        if not begin <= publication_time(published) < end:
            continue
        event = row[5].isoformat() if isinstance(row[5], datetime) else row[5]
        articles.append(dict(meta, id=row[0], title=row[1], url=row[2], excerpt=row[3],
                             publishedAt=published, eventAt=event, timezone=row[6], name=row[8]))
    return articles, {'start': begin.isoformat(), 'endExclusive': end.isoformat(),
                      'basis': 'previous_complete_berlin_source_publication_day'}


def published_context(store, automation):
    from .scoring.events import normalize_event_key
    urls, events = set(), set()
    for issue in store.published():
        if issue.get('synthetic') is False:
            urls.update(s['url'] for s in issue['sources'])
    events.update(row[0] for row in automation.execute('SELECT event_key FROM automation_events').fetchall())
    if store.postgres:
        rows = store.execute("SELECT stats->'review' FROM pipeline_runs WHERE stats->'review' IS NOT NULL").fetchall()
        for (review,) in rows:
            events.update(normalize_event_key(c['eventKey']) for c in review.get('classifications', [])
                          if c.get('eventKey'))
    return urls, sorted(events)


def _preserve_legacy_budget(budget, cfg, now):
    legacy = ROOT / cfg.get('legacyBudgetPath', 'artifacts/mvp3/budget.json')
    month = cfg.get('legacyBudgetMonth', '2026-11')
    if legacy.is_file():
        budget.import_legacy(legacy, month=month)
    elif aware_now(now).strftime('%Y-%m') == month:
        raise ValueError('Historical November budget ledger is required before paid execution')
    budget.import_charge('initial-live-2026-11', '2026-11', '0.007022')


def execute(database, *, day=None, dry_run=True, resume=False, scheduled=False,
            allow_paid=False, config=None, now=None, collector=ingest,
            provider_factory=OpenAIProvider):
    cfg = config or configuration()
    local = aware_now(now)
    day = day or local.date().isoformat()
    if date.fromisoformat(day).isoformat() != day or date.fromisoformat(day) > local.date():
        raise ValueError('Edition date must be canonical and cannot be in the future')
    report = {'startedAt': datetime.now(timezone.utc).isoformat(), 'date': day,
              'mode': 'dry-run' if dry_run else 'live', 'scheduled': scheduled,
              'publishedEditionIds': [], 'status': 'running', 'stage': 'authorization'}
    if scheduled:
        report.update(scheduledFor=slot(day).isoformat(),
                      delaySeconds=max(0, int((local-slot(day)).total_seconds())))
    auto = store = budget = None
    run_id = None
    try:
        auto = AutomationStore(database)
        with run_lock(auto, database):
            if scheduled and (local < slot(day) or day < cfg['startDate']):
                report.update(status='not_due'); return report
            # A dry run reads source metadata only: no collection, LLM, ledger or publication writes.
            store = Store(database)
            existing = next((i for i in store.published()
                             if i.get('date') == day and i.get('synthetic') is False), None)
            if existing:
                report.update(status='unchanged', publishedEditionIds=[existing['id']])
                return report
            candidates, window = article_candidates(store, day)
            report.update(sourceWindow=window, candidatesConsidered=len(candidates))
            if dry_run:
                report.update(status='dry_run', stage='plan', paidCalls=0,
                              note='Read-only stored-evidence plan; live run also collects every configured source')
                return report
            if not allow_paid or (scheduled and (cfg.get('unattendedPaidApproved') is not True
                                                     or os.getenv('UNATTENDED_PAID_APPROVED') != 'true')):
                report.update(status='authorization_required', paidCalls=0)
                return report
            if not auto.postgres:
                report.update(status='postgres_required', paidCalls=0)
                return report
            prior = auto.execute("SELECT status FROM automation_runs WHERE issue_date=? AND mode='live' ORDER BY started_at DESC LIMIT 1", (day,)).fetchone()
            if prior and prior[0] in SUCCESS:
                report.update(status='unchanged'); return report
            if prior and not resume:
                report.update(status='resume_required'); return report
            run_id = auto.start_run(day, 'live')
            report['runId'] = run_id
            budget = MonthlyBudget(auto, run_id=run_id, now=now, limit=cfg['monthlyBudgetUSD'])
            _preserve_legacy_budget(budget, cfg, now)
            snapshot_key = 'candidates:' + day
            snapshot = cache_get(auto, snapshot_key) if resume else None
            report['stage'] = 'collection'
            if snapshot is not None and not snapshot['collection'].get('sourcesFailed'):
                candidates = snapshot['articles']
                report['collection'] = snapshot['collection']
                report['collectionReused'] = True
            else:
                report['collection'] = collector(str(ROOT/cfg['registry']), database, 'live')
                if report['collection']['sourcesSucceeded'] == 0:
                    report.update(status='collection_failed'); return report
                candidates, window = article_candidates(store, day)
                cache_put(auto, snapshot_key, {'articles': candidates, 'collection': report['collection']})
            report['candidatesConsidered'] = len(candidates)
            report['duplicateArticles'] = max(0, report['collection']['articlesSeen']-report['collection']['articlesInserted'])
            from .dedup import suppress_previously_published
            urls, events = published_context(store, auto)
            candidates, suppressed = suppress_previously_published(candidates, published_urls=urls,
                                                                   published_event_keys=events)
            report['rejectedStories'] = suppressed
            if not candidates:
                report.update(status='no_evidence', stage='selection'); return report
            if len(candidates) > 300:
                report.update(status='needs_batching', stage='selection',
                              error='More than 300 candidates; none silently discarded')
                return report
            report['stage'] = 'editorial'
            provider = provider_factory(model='gpt-6.1-terra', classification_model='gpt-6-luna',
                verification_model='gpt-6.1-terra', reasoning_effort='low', retries=1,
                max_output_tokens=6000, before_request=budget.before, after_response=budget.after)
            cached = CachedProvider(provider, auto, day, resume)
            from .editorial.live import generate_real_issue
            def retain(draft):
                # Private draft only. Existing validated/published identities cannot be overwritten.
                store.save_draft(draft)
            try:
                draft, review = generate_real_issue(candidates, day, cached, retain,
                    daily_window=True, excluded_event_keys=events)
            except Exception as error:
                if not str(error).startswith('No source-backed industrial stories'):
                    cached.invalidate_last()
                raise
            finally:
                report['editorialTrace'] = getattr(cached, 'editorial_trace', {})
                report['cachedStagesReused'] = cached.reused
            report['selectedStories'] = len(draft['stories'])
            report['verification'] = 'passed'
            report['stage'] = 'publication'
            from .scoring.events import normalize_event_key
            # Publication and event claims use ONE connection/transaction: failure rolls back both.
            with store.db.transaction():
                for item in review['classifications']:
                    event = normalize_event_key(item['eventKey'])
                    store.execute('INSERT INTO automation_events(event_key,issue_id) VALUES(?,?)',
                                  (event, draft['id']))
                store.publish(draft, review)
                from packages.db.revisions import archive_current_issue
                archive_current_issue(store.db, draft['id'], review=review,
                    expected_content=dict(draft, state='published', validated=True))
            report.update(status='published', publishedEditionIds=[draft['id']])
    except AlreadyRunning:
        report.update(status='overlap_skipped')
    except BudgetExceeded as error:
        report.update(status='budget_stopped', error=str(error))
    except Exception as error:
        # Public exceptions omit provider response bodies and configuration values.
        message = str(error)
        status = 'no_eligible_news' if message.startswith('No source-backed industrial stories') else 'failed'
        report.update(status=status, error=type(error).__name__, reason=message[:1500])
        if report['stage'] == 'editorial':
            report['verification'] = 'rejected'
    finally:
        report['endedAt'] = datetime.now(timezone.utc).isoformat()
        if budget:
            report['budget'] = budget.summary()
            rows = auto.execute('''SELECT id,stage,model,attempt,status,estimated_usd,usage
                FROM api_requests WHERE run_id=? ORDER BY created_at,id''', (run_id,)).fetchall()
            report['apiRequests'] = [dict(id=row[0], stage=row[1], model=row[2], attempt=row[3],
                status=row[4], estimatedUSD=float(row[5]), usage=_json(row[6]) if row[6] else None)
                for row in rows]
        if run_id and auto:
            auto.finish_run(run_id, report['status'], report['stage'], redacted(report),
                            redacted(report.get('reason') or report.get('error')))
        if store:
            store.close()
        if auto:
            auto.close()
        safe_report = redacted(report)
        report.clear()
        report.update(safe_report)
    return redacted(report)


def status(database, *, config=None, now=None):
    cfg = config or configuration()
    auto = AutomationStore(database)
    try:
        runs = auto.runs(limit=100)
        completed = [row[0] for row in auto.execute(
            "SELECT DISTINCT issue_date FROM automation_runs WHERE mode='live' AND status IN ('published','unchanged','no_evidence','no_eligible_news')").fetchall()]
        # Recover publication observability even if a process died after commit but before finish_run.
        if auto.postgres or auto.execute("SELECT name FROM sqlite_master WHERE name='issues'").fetchone():
            completed.extend(_json(row[0])['date'] for row in auto.execute(
                "SELECT content FROM issues WHERE state='published' AND validated=?", (True,)).fetchall()
                if _json(row[0]).get('synthetic') is False)
        missing = missed_dates(cfg['startDate'], completed, now)
        from .collectors.discovery import source_inventory
        inventory = source_inventory(ROOT/cfg['registry'])
        return redacted({'timezone': 'Europe/Berlin', 'publicationTime': '07:00',
            'nextScheduledAt': next_slot(now).isoformat(), 'unattendedPaidApproved':
                cfg.get('unattendedPaidApproved') is True and os.getenv('UNATTENDED_PAID_APPROVED') == 'true',
            'missedDates': missing, 'recentRuns': runs, 'sourceInventory': inventory,
            'budget': MonthlyBudget(auto, now=now, limit=cfg['monthlyBudgetUSD']).summary()})
    finally:
        auto.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['run', 'tick', 'status', 'watch'], nargs='?', default='run')
    parser.add_argument('--database')
    parser.add_argument('--config')
    parser.add_argument('--date')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--allow-paid', action='store_true', help='Explicit one-run paid permission; no permission is assumed')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--scheduled', action='store_true')
    parser.add_argument('--report', default='artifacts/daily-status.json')
    args = parser.parse_args(argv)
    load_project_environment()
    database = args.database or os.getenv('DATABASE_URL')
    if not database:
        parser.error('DATABASE_URL or --database is required')
    cfg = configuration(args.config)
    def once():
        if args.command == 'status':
            return status(database, config=cfg)
        scheduled = args.scheduled or args.command in {'tick', 'watch'}
        day = args.date or (latest_due() if scheduled else None)
        result = execute(database, day=day, dry_run=args.dry_run or not args.allow_paid,
                         resume=args.resume, scheduled=scheduled, allow_paid=args.allow_paid, config=cfg)
        if scheduled:
            try:
                result['schedule'] = status(database, config=cfg)
            except Exception as error:
                result['scheduleStatus'] = type(error).__name__
        return result
    while True:
        try:
            result = once()
        except Exception as error:
            result = {'status': 'unavailable', 'error': type(error).__name__,
                      'action': 'Check database connectivity and apply reviewed automation migration before activation'}
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + '.' + str(os.getpid()) + '.tmp')
        temp.write_text(json.dumps(redacted(result), ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        temp.replace(target)
        print(json.dumps(redacted(result), ensure_ascii=False, default=str), flush=True)
        if args.command != 'watch':
            return 1 if result.get('status') in {'failed', 'unavailable', 'collection_failed', 'budget_stopped',
                'needs_batching', 'resume_required', 'postgres_required', 'authorization_required'} else 0
        time.sleep(30)


if __name__ == '__main__':
    raise SystemExit(main())
