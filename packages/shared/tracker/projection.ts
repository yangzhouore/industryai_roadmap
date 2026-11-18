import type {PublicIssue, PublicSource, Story} from '../index';
import {canonicalIssueHash, projectPublicIssue} from '../public-display';
import catalog from './catalog.json';
import {trackerStages, type TrackerData, type TrackerEvidenceStatus, type TrackerMilestoneView, type TrackerStage, type TrackerTopic} from './types';

const projectIdPattern = /^project-[a-f0-9]{24}$/;
const milestoneIdPattern = /^milestone-[a-f0-9]{24}$/;

interface TrackerEvidenceSnapshot {
  sourceKey: string;
  kind: string;
  publisher: string;
  canonicalUrl: string;
  publishedAt: Date;
  eventAt: Date | null;
  sourceTimezone: string;
}

export interface TrackerRevisionRecord {
  issue: {id: string; slug: string; state: string; validated: boolean; content: unknown};
  issueHash: string;
  storyId: string;
  stage: string;
  withdrawn: boolean;
  evidence: TrackerEvidenceSnapshot[];
  companies: {companyId: string}[];
  technologies: {technologyId: string}[];
}

function searchable(text: string): string {
  return text.normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
}

function mentioned(alias: string, text: string): boolean {
  const term = searchable(alias);
  if (!term) return false;
  return /\p{Script=Han}/u.test(term) ? text.includes(term) : ` ${text} `.includes(` ${term} `);
}

function supportedTopics(ids: string[], topics: typeof catalog.companies, approvedText: string[]): string[] {
  const values = approvedText.map(searchable);
  return topics.filter(topic => ids.includes(topic.id) && [topic.name.en, topic.name.zh, ...topic.aliases]
    .some(alias => values.some(value => mentioned(alias, value)))).map(topic => topic.id);
}

function matchesSource(snapshot: TrackerEvidenceSnapshot, source: PublicSource): boolean {
  return snapshot.publisher === source.name && snapshot.canonicalUrl === source.url
    && snapshot.publishedAt.getTime() === Date.parse(source.publishedAt)
    && (snapshot.eventAt?.getTime() ?? null) === (source.eventAt === null ? null : Date.parse(source.eventAt))
    && snapshot.sourceTimezone === source.timezone;
}

function evidenceStatus(evidence: TrackerEvidenceSnapshot[]): TrackerEvidenceStatus {
  const independent = evidence.filter(item => item.kind === 'independent');
  const publishers = new Set(independent.map(item => searchable(item.publisher)));
  const hosts = new Set(independent.map(item => new URL(item.canonicalUrl).hostname.replace(/^www\./, '')));
  if (publishers.size >= 2 && hosts.size >= 2) return 'independently_verified';
  return evidence.every(item => item.kind === 'vendor') ? 'vendor_claim' : 'reported';
}

function timelineEntry(id: string, projectId: string, issue: PublicIssue, story: Story, options: {
  sources: PublicSource[];
  stage: TrackerStage;
  status: TrackerEvidenceStatus;
  companyIds: string[];
  technologyIds: string[];
}): TrackerMilestoneView {
  const dates = options.sources.flatMap(source => source.eventAt ? [Date.parse(source.eventAt)] : []);
  const eventAt = dates.length && dates.every(time => time === dates[0]) ? new Date(dates[0]).toISOString() : null;
  const publishedAt = new Date(Math.min(...options.sources.map(source => Date.parse(source.publishedAt)))).toISOString();
  return {id, projectId, title: {...story.title}, summary: {...story.summary}, eventAt, publishedAt, issueSlug: issue.slug, ...options};
}

export function projectTrackerMilestone(
  id: string, projectId: string, revision: TrackerRevisionRecord | undefined, policy: unknown,
): TrackerMilestoneView | null {
  if (!projectIdPattern.test(projectId) || !milestoneIdPattern.test(id) || !revision || revision.withdrawn) return null;
  const {issue} = revision;
  if (issue.state !== 'published' || !issue.validated) return null;
  const approved = projectPublicIssue(issue.content, policy);
  if (!approved || approved.synthetic || approved.id !== issue.id || approved.slug !== issue.slug
    || canonicalIssueHash(issue.content) !== revision.issueHash) return null;
  const story = approved.stories.find(item => item.id === revision.storyId);
  const stage = trackerStages.find(value => value === revision.stage);
  if (!story || !stage || story.maturity !== stage || revision.evidence.length !== story.sourceIds.length) return null;
  const evidence = new Map(revision.evidence.map(item => [item.sourceKey, item]));
  const approvedSources = new Map(approved.sources.map(source => [source.id, source]));
  const sources: PublicSource[] = [];
  for (const key of story.sourceIds) {
    const source = approvedSources.get(key);
    const snapshot = evidence.get(key);
    if (!source || !snapshot || !['vendor', 'independent', 'other'].includes(snapshot.kind) || !matchesSource(snapshot, source)) return null;
    sources.push(source);
  }
  return timelineEntry(id, projectId, approved, story, {
    sources, stage, status: evidenceStatus(revision.evidence),
    companyIds: supportedTopics(revision.companies.map(item => item.companyId), catalog.companies, [story.company, story.title.en, story.title.zh]),
    technologyIds: supportedTopics(revision.technologies.map(item => item.technologyId), catalog.technologies,
      [story.category, story.title.en, story.title.zh, story.summary.en, story.summary.zh]),
  });
}

const demoProjects = [
  {companyId: 'demo-factory', projectId: 'demo-visual-inspection', name: {en: 'Demo Factory', zh: '示例工厂'}, technologyIds: []},
  {companyId: 'demo-robotics', projectId: 'demo-robot-handoff', name: {en: 'Demo Robotics', zh: '示例机器人'}, technologyIds: ['physical-ai']},
  {companyId: 'demo-grid', projectId: 'demo-demand-forecasting', name: {en: 'Demo Grid', zh: '示例电网'}, technologyIds: []},
];

export function projectTrackerFixtures(issues: unknown[]): TrackerData {
  const milestones: TrackerMilestoneView[] = [];
  for (const value of issues) {
    const issue = projectPublicIssue(value, null, true);
    if (!issue?.synthetic) continue;
    for (const story of issue.stories) {
      const demo = demoProjects.find(project => project.name.en === story.company);
      const stage = trackerStages.find(value => value === story.maturity);
      if (!demo || !stage) continue;
      const sources = issue.sources.filter(source => story.sourceIds.includes(source.id));
      milestones.push(timelineEntry(story.id, demo.projectId, issue, story, {
        sources, stage, status: 'synthetic', companyIds: [demo.companyId], technologyIds: demo.technologyIds,
      }));
    }
  }
  return trackerData(milestones, true);
}

export function trackerData(entries: TrackerMilestoneView[], synthetic = false): TrackerData {
  const ordered = [...entries].sort((a, b) =>
    Date.parse(b.eventAt ?? b.publishedAt) - Date.parse(a.eventAt ?? a.publishedAt) || a.id.localeCompare(b.id));
  const projects = new Map<string, TrackerData['projects'][number]>();
  for (const entry of ordered) {
    const project = projects.get(entry.projectId) ?? {id: entry.projectId, name: entry.title, companyIds: [], technologyIds: []};
    project.companyIds = [...new Set([...project.companyIds, ...entry.companyIds])];
    project.technologyIds = [...new Set([...project.technologyIds, ...entry.technologyIds])];
    projects.set(project.id, project);
  }
  const topic = ({id, name}: TrackerTopic) => ({id, name: {en: name.en, zh: name.zh}});
  const companies = catalog.companies.map(topic);
  if (synthetic) companies.push(...demoProjects.map(({companyId, name}) => topic({id: companyId, name})));
  return {synthetic, companies, technologies: catalog.technologies.map(topic), projects: [...projects.values()], milestones: ordered};
}
