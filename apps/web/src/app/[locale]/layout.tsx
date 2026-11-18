import type {Metadata} from 'next';
import {NextIntlClientProvider} from 'next-intl';
import {setRequestLocale} from 'next-intl/server';
import Link from 'next/link';
import {notFound} from 'next/navigation';
import {Suspense} from 'react';
import Navigation from '@/components/navigation';
import {isLocale,label,siteUrl} from '@/lib/data';
import '../globals.css';
import '../tracker.css';
export const metadata:Metadata={metadataBase:new URL(siteUrl),title:{default:'Industrial AI Digest',template:'%s · Industrial AI Digest'},description:'A bilingual briefing on AI in manufacturing, robotics and industrial systems.'};
export default async function Layout({children,params}:{children:React.ReactNode;params:Promise<{locale:string}>}){
  const {locale}=await params;if(!isLocale(locale))notFound();
  setRequestLocale(locale);
  const messages=locale==='en'?{home:'Industrial AI Digest home',navigation:'Main navigation',archive:'Archive',methodology:'Our approach',search:'Search',tracker:'Tracker'}:{home:'工业智能简报首页',navigation:'主导航',archive:'往期期刊',methodology:'编辑方法',search:'搜索',tracker:'追踪'};
  return <html lang={locale}><body><NextIntlClientProvider locale={locale} messages={messages}><a className="skip-link" href="#main">{label(locale,'Skip to content','跳至正文')}</a><div className="shell"><Suspense><Navigation locale={locale}/></Suspense>{children}<footer className="site-footer"><div><Link className="footer-brand" href={`/${locale}`}>INDUSTRIAL AI DIGEST<span className="accent">.</span></Link><p>{label(locale,'Intelligence for the people building what’s next.','为建设未来的人们提供工业智能洞察。')}</p></div><nav aria-label={label(locale,'Footer navigation','页脚导航')}><Link href={`/${locale}/archive`}>{label(locale,'Archive','往期期刊')}</Link><Link href={`/${locale}/methodology`}>{label(locale,'Methodology','编辑方法')}</Link><Link href={`/${locale}/whatsnew`}>{label(locale,'What’s new','更新记录')}</Link><Link href={`/${locale}/privacy`}>{label(locale,'Privacy','隐私')}</Link><a href={`/${locale}/rss.xml`}>RSS ↗</a></nav><div className="footer-bottom"><span>© {new Date().getFullYear()} Industrial AI Digest</span><span>{label(locale,'Independent perspective. Traceable evidence.','独立视角，可追溯证据。')}</span></div></footer></div></NextIntlClientProvider></body></html>;
}
