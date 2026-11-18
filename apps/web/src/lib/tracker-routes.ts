import type {Locale, TrackerProjectView, TrackerTopic} from '@industrial/shared';
import type {Metadata} from 'next';
import {notFound} from 'next/navigation';
import {label,siteUrl} from './data';
import {getTrackerData} from './tracker-data';

export const trackerSections = ['companies', 'technologies', 'projects'] as const;
export type TrackerSection = typeof trackerSections[number];

export const trackerCopy = {
  overview: {en: 'Industrial AI Tracker', zh: '工业 AI 追踪'},
  companies: {en: 'Company Tracker', zh: '企业追踪'},
  technologies: {en: 'Technology Tracker', zh: '技术追踪'},
  projects: {en: 'Deployment Tracker', zh: '部署追踪'},
};

export function trackerDescription(locale: Locale, section?: TrackerSection) {
  if (section === 'companies') return label(locale, 'Follow industrial AI companies and the milestones they are linked to.', '追踪工业 AI 企业及其相关里程碑。');
  if (section === 'technologies') return label(locale, 'Follow technologies across research, pilots and industrial use.', '追踪技术从研究、试点到工业应用的进展。');
  if (section === 'projects') return label(locale, 'Follow industrial AI projects from research to commercialization.', '追踪工业 AI 项目从研究到商业化的进展。');
  return label(locale, 'Explore companies, technologies and projects through dated milestones and their original sources.', '通过有日期的里程碑和原始来源，了解企业、技术与项目进展。');
}

export async function resolveTrackerPage(path: string[]) {
  if (path.length > 3 || (path.length > 1 && !trackerSections.some(section => section === path[1]))) notFound();
  const section = path[1] as TrackerSection | undefined;
  const data = await getTrackerData();
  const entry: TrackerTopic | TrackerProjectView | undefined = section && path[2]
    ? data[section].find(item => item.id === path[2])
    : undefined;
  if (path.length === 3 && !entry) notFound();
  return {data, section, entry};
}

export async function trackerMetadata(locale: Locale, path: string[]): Promise<Metadata> {
  const {section, entry} = await resolveTrackerPage(path);
  const suffix = `/${path.join('/')}`;
  const url = `/${locale}${suffix}`;
  const title = entry?.name[locale] ?? trackerCopy[section ?? 'overview'][locale];
  const description = trackerDescription(locale, section);
  return {
    title,
    description,
    alternates: {canonical: url, languages: {en: `/en${suffix}`, zh: `/zh${suffix}`}},
    openGraph: {title, description, url: `${siteUrl}${url}`, locale: locale === 'en' ? 'en_GB' : 'zh_CN', type: 'website'},
  };
}
