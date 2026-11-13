import type {Issue, Locale} from '@industrial/shared';
import {cache} from 'react';
import fixtures from '../../../../packages/shared/fixtures/issues.json';

export const locales: Locale[] = ['en','zh'];
export function isLocale(value:string): value is Locale {return locales.includes(value as Locale);}
export const siteUrl = process.env.SITE_URL || 'http://localhost:3000';
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
export const getIssues=cache(async function getIssues():Promise<Issue[]> {
  let rows:unknown[];
  const fixtureMode=process.env.DATA_MODE==='fixture';
  if (fixtureMode) rows=fixtures;
  else {
    const {PrismaClient}=await import('@industrial/db');
    const db=new PrismaClient();
    try {rows=(await db.digestIssue.findMany({where:{state:'published',validated:true,content:{path:['synthetic'],equals:false}}})).map((row:{content:unknown})=>row.content);}
    finally {await db.$disconnect();}
  }
  return rows.filter(validIssue).filter(issue=>fixtureMode||(
    issue.synthetic===false&&issue.sources.every(source=>source.synthetic===false)&&
    issue.stories.every(story=>story.evidenceStatus==='verified'&&
      (!("synthetic" in story)||story.synthetic===false))
  )).sort((a,b)=>b.date.localeCompare(a.date));
});
export function dateLabel(date:string, locale:Locale){return new Intl.DateTimeFormat(locale==='en'?'en-GB':'zh-CN',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(date+'T00:00:00Z'));}
export function label(locale:Locale,en:string,zh:string){return locale==='en'?en:zh;}
export function categoryLabel(category:string,locale:Locale){const names:Record<string,string>={'Manufacturing AI':'制造业 AI','Robotics & Physical AI':'机器人与物理 AI','Digital Twins & Simulation':'数字孪生与仿真','Energy & Infrastructure AI':'能源与基础设施 AI','Industrial Agents & Copilots':'工业智能体与助手','Industrial Edge AI':'工业边缘 AI','Industrial AI Business & Policy':'工业 AI 商业与政策'};return locale==='zh'?(names[category]||category):category;}
export function maturityLabel(stage:string,locale:Locale){const names:Record<string,string>={research:'研究',prototype:'原型',pilot:'试点',deployed:'已部署',scaling:'规模化',commercial:'商业化'};return locale==='zh'?(names[stage]||stage):stage;}
