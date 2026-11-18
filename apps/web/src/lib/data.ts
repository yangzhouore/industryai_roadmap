import 'server-only';
import type {Locale, PublicIssue} from '@industrial/shared';
import {projectPublicIssue} from '../../../../packages/shared/public-display';
export {validIssue, canonicalIssueHash, validPublicPolicy, projectPublicIssue} from '../../../../packages/shared/public-display';
import publicDisplayPolicy from '../../../../config/public-display.json';
import {cache} from 'react';
import fixtures from '../../../../packages/shared/fixtures/issues.json';

export const locales: Locale[] = ['en','zh'];
export function isLocale(value:string): value is Locale {return locales.includes(value as Locale);}
export const siteUrl = process.env.SITE_URL || 'http://localhost:3000';
export const getIssues=cache(async function getIssues():Promise<PublicIssue[]> {
  let rows:unknown[];
  const fixtureMode=process.env.DATA_MODE==='fixture';
  if (fixtureMode) rows=fixtures;
  else {
    const {PrismaClient}=await import('@industrial/db');
    const db=new PrismaClient();
    try {rows=(await db.digestIssue.findMany({where:{state:'published',validated:true,content:{path:['synthetic'],equals:false}}})).map((row:{content:unknown})=>row.content);}
    finally {await db.$disconnect();}
  }
  return rows.map(issue=>projectPublicIssue(issue,publicDisplayPolicy,fixtureMode)).filter((issue):issue is PublicIssue=>issue!==null).sort((a,b)=>b.date.localeCompare(a.date));
});
export function dateLabel(date:string, locale:Locale){return new Intl.DateTimeFormat(locale==='en'?'en-GB':'zh-CN',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(date+'T00:00:00Z'));}
export function label(locale:Locale,en:string,zh:string){return locale==='en'?en:zh;}
export function categoryLabel(category:string,locale:Locale){const names:Record<string,string>={'Manufacturing AI':'制造业 AI','Robotics & Physical AI':'机器人与物理 AI','Digital Twins & Simulation':'数字孪生与仿真','Energy & Infrastructure AI':'能源与基础设施 AI','Industrial Agents & Copilots':'工业智能体与助手','Industrial Edge AI':'工业边缘 AI','Industrial AI Business & Policy':'工业 AI 商业与政策'};return locale==='zh'?(names[category]||category):category;}
export function maturityLabel(stage:string,locale:Locale){const names:Record<string,string>={research:'研究',prototype:'原型',pilot:'试点',deployed:'已部署',scaling:'规模化',commercial:'商业化'};return locale==='zh'?(names[stage]||stage):stage;}
