import type {MetadataRoute} from 'next';
import {getIssues,locales,siteUrl} from '@/lib/data';
export const dynamic='force-dynamic';
export default async function sitemap():Promise<MetadataRoute.Sitemap>{const issues=await getIssues();const paths=['','/archive','/search','/methodology','/whatsnew','/privacy',...issues.flatMap(i=>[`/digest/${i.slug}`,`/digest/${i.slug}/sources`])];return locales.flatMap(locale=>paths.map(path=>({url:`${siteUrl}/${locale}${path}`,alternates:{languages:{en:`${siteUrl}/en${path}`,zh:`${siteUrl}/zh${path}`}}})));}
