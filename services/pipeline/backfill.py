"""Explicit historical backfill; never invoked by unattended daily workflows."""
import argparse
from datetime import date,datetime,timedelta
import json
import os
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
from .config import load_project_environment
from .budget import Budget,BudgetExceeded
from .store import Store
from .editorial.provider import OpenAIProvider
from .editorial.live import generate_real_issue

ROOT=Path('artifacts/mvp3')

def execute(args):
    load_project_environment();ROOT.mkdir(parents=True,exist_ok=True)
    budget=Budget(limit=args.max_cost_usd)
    store=Store(os.environ['DATABASE_URL'])
    state_path=ROOT/'progress.json'
    state=json.loads(state_path.read_text()) if state_path.exists() else {'days':{}}
    if args.dry_run:
        state_path=ROOT/'dry-run.json'
    first,last=date.fromisoformat(args.start),date.fromisoformat(args.end)
    if first>last: raise ValueError('Start follows end')
    zone=ZoneInfo('Europe/Berlin')
    rows=store.execute("SELECT raw_metadata FROM raw_articles WHERE raw_metadata->>'synthetic'='false' ORDER BY published_at DESC").fetchall()
    byday={}
    for row in rows:
        article=row[0];stamp=datetime.fromisoformat(article['publishedAt'].replace('Z','+00:00'))
        day=stamp.astimezone(zone).date().isoformat();byday.setdefault(day,[]).append(article)
    selected=[first+timedelta(days=i) for i in range((last-first).days+1)]
    if args.date: selected=[date.fromisoformat(args.date)]
    if any(day<first or day>last for day in selected):
        raise ValueError('--date must lie within --start and --end')
    for day in selected:
        key=day.isoformat();articles=byday.get(key,[])
        prior=state['days'].get(key,{})
        if args.resume and prior.get('status')=='published': continue
        existing=store.execute("SELECT id,content FROM issues WHERE issue_date=? AND state='published'",(key,)).fetchone()
        if existing and existing[1].get('synthetic') is False and existing[0].endswith('-historical'):
            state['days'][key]={'status':'published','articles':len(articles),'unchanged':True};continue
        info={'articles':len(articles),'status':'no_accessible_evidence'}
        state['days'][key]=info
        if len(articles)>30:
            info.update(status='blocked',error='More than30 candidates: batching required; no silent truncation')
        elif articles and args.dry_run:
            info['status']='eligible_dry_run'
        elif articles:
            before=budget.spent
            provider=OpenAIProvider(model='gpt-6.1-terra',classification_model='gpt-6-luna',verification_model='gpt-6.1-terra',retries=0,max_output_tokens=6000,timeout=120,before_request=budget.before,after_response=budget.after)
            post=provider._post
            cache=ROOT/'responses';cache.mkdir(exist_ok=True)
            def cached_post(payload):
                name=sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                path=cache/(name+'.json')
                if path.exists():
                    response=json.loads(path.read_text(encoding='utf-8'));response.pop('usage',None)
                    return response
                response=post(payload)
                path.write_text(json.dumps(response,ensure_ascii=False,indent=2),encoding='utf-8')
                return response
            provider._post=cached_post
            def retain(draft):
                (ROOT/(key+'-draft.json')).write_text(json.dumps(draft,ensure_ascii=False,indent=2),encoding='utf-8')
            try:
                draft,review=generate_real_issue(articles,key,provider,retain,strict_day=True)
                from packages.db.revisions import archive_current_issue
                with store.db.transaction():
                    store.execute('SELECT pg_advisory_xact_lock(hashtext(?))',('backfill:'+key,))
                    old=store.execute("SELECT id,content FROM issues WHERE issue_date=?",(key,)).fetchone()
                    if old:
                        revision=archive_current_issue(store.db,old[0],expected_content=old[1])
                        # Retain original content and all normalized evidence. Only release
                        # its current-edition keys after the append-only revision is saved.
                        suffix='-previous-'+str(revision)
                        store.execute("UPDATE issues SET slug=slug||?,issue_date=issue_date||?,state='validated' WHERE id=?",(suffix,suffix,old[0]))
                    store.publish(draft,review)
                    full_trace=getattr(provider,'editorial_trace',{}).get('classifications',[])
                    for story in draft['stories']:
                        chosen=next(c for c in review['classifications'] if c['articleId'] in story['sourceIds'])
                        for item in full_trace:
                            if item.get('eventKey') and item['eventKey']==chosen.get('eventKey'):
                                store.execute('INSERT INTO article_cluster_links(cluster_id,article_id) VALUES(?,?) ON CONFLICT DO NOTHING',
                                              (draft['id']+':'+story['id'],item['articleId']))
                info.update(status='published',stories=len(draft['stories']),slug=draft['slug'],reviewRequests=review['requests'])
                (ROOT/(key+'-review.json')).write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
            except BudgetExceeded as error:
                info.update(status='budget_stopped',error=str(error))
            except Exception as error:
                info.update(status='unpublished',error=type(error).__name__,message=str(error)[:1000])
                if str(error).startswith('No source-backed industrial stories'):
                    info['status']='no_eligible_news'
            info['estimatedUSD']=budget.spent-before
            info['editorialTrace']=getattr(provider,'editorial_trace',{})
        state.update(estimatedUSD=budget.spent,budgetUSD=budget.data['limit'])
        state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({key:info,'estimatedUSD':budget.spent}),flush=True)
        if info['status']=='budget_stopped':break
    state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    if not args.dry_run:
        store.log_run('backfill','complete_with_gaps',state)
    store.close()
    return state

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start',default='2026-11-01');parser.add_argument('--end',default='2026-11-13')
    parser.add_argument('--date');parser.add_argument('--resume',action='store_true');parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--max-cost-usd',type=float,default=2)
    args=parser.parse_args()
    ROOT.mkdir(parents=True,exist_ok=True)
    lock=ROOT/'backfill.lock'
    descriptor=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try: execute(args)
    finally:os.close(descriptor);lock.unlink()
if __name__=='__main__':main()
