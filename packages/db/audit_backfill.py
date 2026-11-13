"""Read-only Berlin-day coverage audit. Prints attribution/date metadata, no prose."""
import argparse
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
import os
from zoneinfo import ZoneInfo
import psycopg

BERLIN = ZoneInfo('Europe/Berlin')


def day_bounds(day: str):
    value = date.fromisoformat(day)
    return (datetime.combine(value,time.min,BERLIN).astimezone(timezone.utc),
            datetime.combine(value+timedelta(days=1),time.min,BERLIN).astimezone(timezone.utc))


def eligible_on_day(published_at: str | datetime, day: str) -> bool:
    stamp = datetime.fromisoformat(published_at.replace('Z','+00:00')) if isinstance(published_at,str) else published_at
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError('Publication timestamp must carry a timezone')
    start,end = day_bounds(day)
    return start <= stamp < end


def audit(db, start='2026-11-01', end='2026-11-13'):
    first,last = date.fromisoformat(start),date.fromisoformat(end)
    if first > last:
        raise ValueError('Start must not follow end')
    records=[]
    for offset in range((last-first).days+1):
        day=(first+timedelta(days=offset)).isoformat()
        begin,finish=day_bounds(day)
        count=db.execute('SELECT count(*) FROM raw_articles WHERE published_at >= %s AND published_at < %s AND coalesce((raw_metadata->>\'synthetic\')::boolean,false)=false',(begin,finish)).fetchone()[0]
        records.append({'date':day,'articles':count})
    issues=[]
    snapshot=[]
    for row in db.execute('SELECT id,issue_date,state,validated,content FROM issues ORDER BY issue_date,id'):
        issue_id,day,state,validated,content=row
        snapshot.append({'id':issue_id,'content':content,'state':state,'validated':validated})
        if content.get('synthetic'):
            continue
        outliers=[{'id':s['id'],'url':s['url'],'publishedAt':s['publishedAt']}
                  for s in content.get('sources',[]) if not eligible_on_day(s['publishedAt'],day)]
        issues.append({'id':issue_id,'date':day,'state':state,'validated':validated,
                       'sourceCount':len(content.get('sources',[])),'offDaySources':outliers})
    return {'timezone':'Europe/Berlin','start':start,'end':end,'days':records,'issues':issues,
            'allIssuesDigest':sha256(json.dumps(snapshot,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
            'allIssueCount':len(snapshot)}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start',default='2026-11-01')
    parser.add_argument('--end',default='2026-11-13')
    args=parser.parse_args()
    with psycopg.connect(os.environ['DATABASE_URL'],autocommit=True) as db:
        print(json.dumps(audit(db,args.start,args.end),ensure_ascii=False,indent=2))
