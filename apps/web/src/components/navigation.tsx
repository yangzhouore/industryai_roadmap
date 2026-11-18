'use client';
import Link from 'next/link';
import {usePathname,useSearchParams} from 'next/navigation';
import {useTranslations} from 'next-intl';
import type {Locale} from '@industrial/shared';

export default function Navigation({locale}:{locale:Locale}) {
  const path=usePathname(); const query=useSearchParams(); const t=useTranslations();
  const other=locale==='en'?'zh':'en';
  const trackerHref=`/${locale}/tracker`;
  const trackerCurrent=path===trackerHref?'page':path.startsWith(`${trackerHref}/`)?'location':undefined;
  const alternate=path.replace(/^\/(en|zh)(?=\/|$)/,`/${other}`)+(query.toString()?`?${query.toString()}`:'');
  return <header className="site-header"><Link className="brand" href={`/${locale}`} aria-label={t('home')}><span className="brand-mark" aria-hidden="true">i<span>•</span></span><span>INDUSTRIAL AI<span className="brand-sub">DIGEST / 工业智能简报</span></span></Link><nav aria-label={t('navigation')}><Link href={`/${locale}/archive`} aria-current={path.endsWith('/archive')?'page':undefined}>{t('archive')}</Link><Link href={trackerHref} aria-current={trackerCurrent}>{t('tracker')}</Link><Link href={`/${locale}/methodology`} aria-current={path.endsWith('/methodology')?'page':undefined}>{t('methodology')}</Link><Link className="search-link" href={`/${locale}/search`} aria-label={t('search')}><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></svg><span>{t('search')}</span></Link><Link className="language" href={alternate} hrefLang={other} lang={other}>{other==='zh'?'中文':'EN'} <span aria-hidden="true">↗</span></Link></nav></header>;
}
