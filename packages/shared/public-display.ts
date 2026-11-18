import type {Issue, PublicIssue, PublicDisplayPolicy, Text} from './index';
import {createHash} from 'node:crypto';

function record(value:unknown):value is Record<string,unknown>{return Boolean(value)&&typeof value==='object'&&!Array.isArray(value);}
function textPair(value:unknown):boolean{return record(value)&&typeof value.en==='string'&&Boolean(value.en.trim())&&typeof value.zh==='string'&&Boolean(value.zh.trim());}
function safeSourceUrl(value:unknown,synthetic:boolean):boolean{if(typeof value!=='string')return false;try{const url=new URL(value);return url.protocol==='https:'&&!url.username&&!url.password&&(synthetic?url.hostname==='example.org'&&url.pathname.startsWith('/fixtures/'):url.hostname!=='example.org');}catch{return false;}}
export function validIssue(value:unknown): value is Issue {
  if (!record(value)) return false;
  const i=value;
  if(i.state!=='published'||i.validated!==true||typeof i.synthetic!=='boolean'||typeof i.id!=='string'||!i.id||typeof i.slug!=='string'||!/^[a-z0-9][a-z0-9-]*$/.test(i.slug)||typeof i.date!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(i.date)||!Number.isFinite(Date.parse(i.date))||!textPair(i.title)||!textPair(i.introduction)||!Array.isArray(i.sources)||!Array.isArray(i.stories)||!i.stories.length)return false;
  const sourceIds=new Set<string>();const storyIds=new Set<string>();
  for(const s of i.sources){if(!record(s)||typeof s.id!=='string'||!s.id||sourceIds.has(s.id)||typeof s.name!=='string'||!s.name||typeof s.synthetic!=='boolean'||s.synthetic!==i.synthetic||!safeSourceUrl(s.url,s.synthetic)||typeof s.publishedAt!=='string'||!Number.isFinite(Date.parse(s.publishedAt))||(s.eventAt!==null&&(typeof s.eventAt!=='string'||!Number.isFinite(Date.parse(s.eventAt))))||typeof s.timezone!=='string'||!s.timezone||!textPair(s.excerpt))return false;sourceIds.add(s.id);}
  let features=0;
  for(const s of i.stories){if(!record(s)||typeof s.id!=='string'||!s.id||storyIds.has(s.id)||!textPair(s.title)||!textPair(s.summary)||!textPair(s.why)||!textPair(s.limitation)||typeof s.category!=='string'||!s.category||typeof s.company!=='string'||!s.company||!['research','prototype','pilot','deployed','scaling','commercial'].includes(String(s.maturity))||!['feature','quick_bite'].includes(String(s.kind))||s.evidenceStatus!==(i.synthetic?'synthetic':'verified')||typeof s.score!=='number'||!Number.isFinite(s.score)||s.score<0||s.score>100||!Array.isArray(s.sourceIds)||!s.sourceIds.length||new Set(s.sourceIds).size!==s.sourceIds.length||!s.sourceIds.every(id=>typeof id==='string'&&sourceIds.has(id)))return false;if(s.kind==='feature')features++;storyIds.add(s.id);}
  return features<=3;
}
// Full stored JSON binds review to exact content; projection forwards only known fields.
export function canonicalIssueHash(value:unknown):string {
  const seen=new Set<object>();
  function serialize(item:unknown):string {
    if(item===null||typeof item==='boolean'||typeof item==='string')return JSON.stringify(item);
    if(typeof item==='number'&&Number.isFinite(item))return JSON.stringify(item);
    if(typeof item!=='object'||!item)throw new Error('Non-JSON content');
    if(seen.has(item))throw new Error('Cyclic content');
    const proto=Object.getPrototypeOf(item);
    if(!Array.isArray(item)&&proto!==null&&
      (Object.getPrototypeOf(proto)!==null||!Object.hasOwn(proto,'constructor')||proto.constructor.name!=='Object'))throw new Error('Non-JSON prototype');
    if(Array.isArray(item)&&(!Array.isArray(proto)||!Object.hasOwn(proto,'constructor')||proto.constructor.name!=='Array'))throw new Error('Non-JSON array prototype');
    if(Object.getOwnPropertySymbols(item).length)throw new Error('Non-JSON fields');
    for(const key of Object.keys(item))if(!Object.hasOwn(Object.getOwnPropertyDescriptor(item,key)||{},'value'))throw new Error('Non-JSON accessor');
    seen.add(item);
    let result:string;
    if(Array.isArray(item)){
      if(Object.keys(item).length!==item.length)throw new Error('Non-JSON array');
      result='['+Array.from(item,serialize).join(',')+']';
    }else result='{'+Object.keys(item).sort().map(key=>JSON.stringify(key)+':'+serialize((item as Record<string,unknown>)[key])).join(',')+'}';
    seen.delete(item);
    return result;
  }
  return createHash('sha256').update(serialize(value),'utf8').digest('hex');
}
function nonblank(value:unknown):value is string{return typeof value==='string'&&Boolean(value.trim());}
function evidenceUrl(value:unknown):boolean {
  if(!nonblank(value))return false;
  try{const url=new URL(value);return url.protocol==='https:'&&Boolean(url.hostname)&&!url.username&&!url.password;}catch{return false;}
}
function reviewDate(value:unknown):boolean {
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z)?$/.test(value))return false;
  const time=Date.parse(value);
  return Number.isFinite(time)&&time<=Date.now()&&new Date(time).toISOString().slice(0,10)===value.slice(0,10);
}
export function validPublicPolicy(value:unknown):value is PublicDisplayPolicy {
  if(!record(value)||value.version!==1||value.intendedUse!=='public-web'||!Array.isArray(value.editions))return false;
  const ids=new Set<string>();
  for(const edition of value.editions){
    if(!record(edition)||!nonblank(edition.issueId)||ids.has(edition.issueId)||
      typeof edition.contentSha256!=='string'||!/^[a-f0-9]{64}$/.test(edition.contentSha256)||
      typeof edition.editorialApproved!=='boolean'||!nonblank(edition.reviewedBy)||!reviewDate(edition.reviewedAt)||
      !evidenceUrl(edition.reviewEvidence)||!Array.isArray(edition.sourceLinks))return false;
    ids.add(edition.issueId);
    const sources=new Set<string>();
    for(const link of edition.sourceLinks){
      if(!record(link)||!nonblank(link.sourceId)||sources.has(link.sourceId)||!evidenceUrl(link.url)||
        !nonblank(link.publisher)||typeof link.approved!=='boolean'||!['permission','legal-review'].includes(String(link.basis))||
        !evidenceUrl(link.evidenceUrl)||!nonblank(link.reviewedBy)||!reviewDate(link.reviewedAt))return false;
      sources.add(link.sourceId);
    }
  }
  return true;
}
function copyText(value:Text):Text{return {en:value.en,zh:value.zh};}
export function projectPublicIssue(value:unknown,policy:unknown,fixtureMode=false):PublicIssue|null {
  try{
    if(!validIssue(value))return null;
    const hash=canonicalIssueHash(value);
    if(value.synthetic){if(!fixtureMode)return null;}
    else{
      if(!validPublicPolicy(policy)||value.stories.some(story=>'synthetic' in story&&story.synthetic!==false))return null;
      const approval=policy.editions.find(edition=>edition.issueId===value.id);
      if(!approval||!approval.editorialApproved||approval.contentSha256!==hash||approval.sourceLinks.length!==value.sources.length)return null;
      if(!value.sources.every(source=>approval.sourceLinks.some(link=>link.sourceId===source.id&&link.url===source.url&&link.publisher===source.name&&link.approved)))return null;
    }
    return {
      id:value.id,slug:value.slug,date:value.date,state:value.state,validated:value.validated,synthetic:value.synthetic,
      title:copyText(value.title),introduction:copyText(value.introduction),
      sources:value.sources.map(source=>({id:source.id,name:source.name,url:source.url,publishedAt:source.publishedAt,
        eventAt:source.eventAt,timezone:source.timezone,synthetic:source.synthetic})),
      stories:value.stories.map(story=>({id:story.id,category:story.category,maturity:story.maturity,company:story.company,
        kind:story.kind,title:copyText(story.title),summary:copyText(story.summary),why:copyText(story.why),
        limitation:copyText(story.limitation),sourceIds:story.sourceIds.map(id=>id),evidenceStatus:story.evidenceStatus,score:story.score}))
    };
  }catch{return null;}
}
