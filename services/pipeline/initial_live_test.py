"""Explicitly invoked, one-article live acceptance run. Never scheduled."""
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from .editorial.provider import OpenAIProvider
from .editorial.live import generate_real_issue
from .store import Store


def main():
    # Read only project configuration, without displaying or persisting secrets.
    for line in Path('.env.local').read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            name,value=line.split('=',1)
            if name.strip() in {'OPENAI_API_KEY','OPENAI_MODEL','DATABASE_URL'}:
                os.environ.setdefault(name.strip(),value.strip().strip('"').strip("'"))
    store=Store(os.getenv('DATABASE_URL','postgresql://digest@127.0.0.1:55432/digest'))
    model=os.getenv('OPENAI_MODEL') or 'gpt-4.1-mini'
    provider=OpenAIProvider(model=model,retries=0,max_output_tokens=4096,timeout=120)
    folder=Path('artifacts/initial-live');folder.mkdir(parents=True,exist_ok=True)
    prior = json.loads((folder/'report.json').read_text(encoding='utf-8')) if (folder/'report.json').exists() else {}
    if prior:
        (folder/('attempt-'+prior['startedAt'].replace(':','-')+'.json')).write_text(json.dumps(prior,ensure_ascii=False,indent=2),encoding='utf-8')
    report={'model':model,'published':0,'startedAt':datetime.now(timezone.utc).isoformat()}
    original=provider._post
    def transport(payload):
        if payload['text']['format']['name']=='industrial_classify' and (folder/'industrial_classify.json').exists():
            cached=json.loads((folder/'industrial_classify.json').read_text(encoding='utf-8'))
            cached.pop('usage',None)
            return cached
        if payload['text']['format']['name']=='industrial_generate':
            payload['instructions'] += '\nFor this small acceptance edition use supplied standardAnalysis and standardLimitation verbatim for why and limitation. Keep summary concise, attribute the vendor announcement, and use exact source quotations.'
        if len(provider.usage)>=3:
            raise RuntimeError('Initial run request budget exhausted')
        response=original(payload)
        (folder/(payload['text']['format']['name']+'.json')).write_text(json.dumps(response,ensure_ascii=False,indent=2),encoding='utf-8')
        return response
    provider._transport=transport
    try:
        day=datetime.now(timezone.utc).date().isoformat()
        existing=[i for i in store.published() if i['date']==day and not i['synthetic']]
        if existing:
            report.update(status='unchanged',slug=existing[0]['slug'])
            return
        row=store.execute("SELECT raw_metadata FROM raw_articles WHERE raw_metadata->>'synthetic'='false' AND source_id='nvidia-robotics' ORDER BY published_at DESC LIMIT 1").fetchone()
        if not row: raise RuntimeError('No collected NVIDIA robotics evidence')
        article=row[0]
        report['sourceUrl']=article['url']
        def retain(draft):
            store.save_draft(draft)
            (folder/'draft.json').write_text(json.dumps(draft,ensure_ascii=False,indent=2),encoding='utf-8')
        draft,review=generate_real_issue([article],datetime.now(timezone.utc).date().isoformat(),provider,retain)
        report['published']=int(store.publish(draft,review))
        report.update(status='published',slug=draft['slug'])
        (folder/'review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
    except Exception as error:
        report.update(status='blocked',error=type(error).__name__,message=str(error)[:1500])
    finally:
        report['requests']=provider.usage
        report['inputTokens']=sum(r['usage'].get('input_tokens',0) for r in provider.usage)
        report['outputTokens']=sum(r['usage'].get('output_tokens',0) for r in provider.usage)
        report['estimatedUSDUpper']=round((report['inputTokens']*.4+report['outputTokens']*1.6)/1_000_000,6) if model.startswith('gpt-4.1-mini') else None
        report['cumulativeInputTokens']=prior.get('cumulativeInputTokens',prior.get('inputTokens',0))+report['inputTokens']
        report['cumulativeOutputTokens']=prior.get('cumulativeOutputTokens',prior.get('outputTokens',0))+report['outputTokens']
        report['cumulativeEstimatedUSDUpper']=round((report['cumulativeInputTokens']*.4+report['cumulativeOutputTokens']*1.6)/1_000_000,6)
        report['endedAt']=datetime.now(timezone.utc).isoformat()
        (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
        store.close()

if __name__=='__main__': main()
