"""Read-only acceptance against the running backfilled PostgreSQL website."""
import json,os,html
from datetime import datetime,date,timedelta
from zoneinfo import ZoneInfo
from urllib.request import urlopen,Request
from urllib.error import HTTPError
from urllib.parse import quote
from services.pipeline.config import load_project_environment
from services.pipeline.store import Store
from services.pipeline.verification.review import issue_digest
from services.pipeline.translation import parity_errors

load_project_environment()
store=Store(os.environ['DATABASE_URL'])
issues={i['date']:i for i in store.published() if not i['synthetic'] and i['id'].endswith('-historical')}
checks=0
for n in range(13):
    day=(date(2026,11,1)+timedelta(days=n)).isoformat()
    for locale in ('en','zh'):
        url=f'http://127.0.0.1:3000/{locale}/digest/{day}'
        if day not in issues:
            try:urlopen(url);raise AssertionError('Unexpected published day '+day)
            except HTTPError as error:assert error.code==404
            checks+=1;continue
        issue=issues[day]
        for suffix in ('','/sources'):
            with urlopen(url+suffix) as response:
                body=html.unescape(response.read().decode());assert response.status==200
                assert 'example.org/fixtures/' not in body
                for source in issue['sources']:
                    if suffix:assert source['url'] in body
            checks+=1
        title=issue['stories'][0]['title'][locale]
        with urlopen(f'http://127.0.0.1:3000/{locale}/search?q='+quote(title)) as response:
            assert issue['slug'] in response.read().decode()
        checks+=1
for issue in issues.values():
    review=store.execute("SELECT stats->'review' FROM pipeline_runs WHERE stats->>'issueId'=? AND stats->'review' IS NOT NULL ORDER BY started_at DESC LIMIT 1",(issue['id'],)).fetchone()[0]
    assert review['issueHash']==issue_digest(issue)
    event_keys=[c['eventKey'] for c in review['classifications']]
    assert len(event_keys)==len(set(event_keys))
    for source in issue['sources']:
        assert datetime.fromisoformat(source['publishedAt'].replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Berlin')).date().isoformat()==issue['date']
        with urlopen(Request(source['url'],method='HEAD'),timeout=30) as response:assert response.status==200
        checks+=1
    for story in issue['stories']:
        for field in ('title','summary','why','limitation'):assert not parity_errors(story[field],field)
        score=store.execute('SELECT final_score FROM scores WHERE cluster_id=?',(issue['id']+':'+story['id'],)).fetchone()[0]
        assert abs(score-story['score'])<.001
for locale in ('en','zh'):
    with urlopen('http://127.0.0.1:3000/'+locale+'/archive') as response:
        body=response.read().decode();positions=[body.index('/digest/'+day) for day in sorted(issues,reverse=True)]
        assert positions==sorted(positions);assert 'example.org/fixtures/' not in body
    checks+=1
report={'checks':checks,'publishedDates':sorted(issues),'revisions':store.execute('SELECT count(*) FROM edition_revisions').fetchone()[0]}
print(json.dumps(report));store.close()
