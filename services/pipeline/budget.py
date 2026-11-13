"""Persistent conservative application budget; incomplete calls retain reservations."""
import json
from pathlib import Path
RATES={'gpt-6-luna':(.10,.01,.125,.50),'gpt-6.1-terra':(1,.05,1.25,5)}
class BudgetExceeded(RuntimeError): pass
class Budget:
    def __init__(self,path='artifacts/mvp3/budget.json',limit=2):
        if not 0<limit<=2: raise ValueError('Authorized ceiling is USD2.00')
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        self.data=json.loads(self.path.read_text()) if self.path.exists() else {'limit':limit,'requests':[]}
        self.data['limit']=min(limit,self.data['limit']); self.pending=None
    @property
    def spent(self): return sum(r['charge'] for r in self.data['requests'])
    def save(self):
        temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(self.data,indent=2));temp.replace(self.path)
    def before(self,context):
        model=context['model']; payload=context['request']
        if model not in RATES: raise BudgetExceeded('Unapproved model; no fallback')
        reserve=((len(json.dumps(payload,ensure_ascii=False).encode())+4096)*RATES[model][2]+payload['max_output_tokens']*RATES[model][3])/1e6
        if self.spent+reserve>self.data['limit']: raise BudgetExceeded('Next request could exceed authorized USD budget')
        self.data['requests'].append({'model':model,'stage':context['stage'],'charge':reserve,'reserved':reserve,'status':'reserved'})
        self.pending=len(self.data['requests'])-1;self.save()
    def after(self,record):
        if not record.get('usage'): return
        if self.pending is None: raise BudgetExceeded('Response without reservation')
        item=self.data['requests'][self.pending];u=record['usage'];rates=RATES[item['model']]
        d=u.get('input_tokens_details',{});c=d.get('cached_tokens',0);w=d.get('cache_write_tokens',0)
        item.update(usage=u,responseId=record.get('responseId'),status='measured',charge=(max(0,u.get('input_tokens',0)-c-w)*rates[0]+c*rates[1]+w*rates[2]+u.get('output_tokens',0)*rates[3])/1e6)
        self.pending=None;self.save()
