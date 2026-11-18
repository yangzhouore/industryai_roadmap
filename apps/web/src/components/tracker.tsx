import type {Locale, PublicSource, TrackerMilestoneView, TrackerProjectView, TrackerTopic} from '@industrial/shared';
import Link from 'next/link';
import {dateLabel,label} from '@/lib/data';
import {resolveTrackerPage,trackerCopy,trackerDescription,trackerSections,type TrackerSection} from '@/lib/tracker-routes';

type TrackerData = Awaited<ReturnType<typeof resolveTrackerPage>>['data'];

const stages = {
  research: {en: 'Research', zh: '研究'},
  prototype: {en: 'Prototype', zh: '原型'},
  pilot: {en: 'Pilot', zh: '试点'},
  deployed: {en: 'Deployment', zh: '部署'},
  scaling: {en: 'Scaling', zh: '规模化'},
  commercial: {en: 'Commercialization', zh: '商业化'},
} satisfies Record<TrackerMilestoneView['stage'], Record<Locale, string>>;

const statuses = {
  vendor_claim: {en: 'Vendor claim', zh: '厂商声明'},
  independently_verified: {en: 'Independently verified', zh: '独立验证'},
  reported: {en: 'Reported', zh: '已报道'},
  synthetic: {en: 'Synthetic demonstration', zh: '模拟演示'},
} satisfies Record<TrackerMilestoneView['status'], Record<Locale, string>>;

const normalize = (text: string) => text.normalize('NFKC').toLocaleLowerCase().trim().replace(/\s+/g, ' ');

function contains(words: string[], terms: string[]) {
  const contents = normalize(words.join(' '));
  return terms.every(term => contents.includes(term));
}

function nameMatches(item: TrackerTopic, terms: string[]) {
  return contains([item.name.en, item.name.zh], terms);
}

function trackerPath(locale: Locale, section?: TrackerSection, id?: string) {
  return `/${locale}/tracker${section ? `/${section}` : ''}${id ? `/${encodeURIComponent(id)}` : ''}`;
}

function Day({value,locale}: {value: string, locale: Locale}) {
  const utcDay = new Date(value).toISOString().slice(0, 10);
  return <time dateTime={value} title={value}>{dateLabel(utcDay, locale)}</time>;
}

function Reference({source,locale}: {source: PublicSource, locale: Locale}) {
  return <li>
    {source.synthetic
      ? <><strong>{source.name}</strong> <span className="synthetic-tag">{label(locale,'Example URL','示例网址')}</span><span className="tracker-example-url">{source.url}</span></>
      : <a className="text-link" href={source.url}>{source.name} <span aria-hidden="true">↗</span></a>}
    <dl className="tracker-source-dates">
      <div><dt>{label(locale,'Published','发布日期')}</dt><dd><Day value={source.publishedAt} locale={locale}/></dd></div>
      <div><dt>{label(locale,'Event date','事件日期')}</dt><dd>{source.eventAt ? <Day value={source.eventAt} locale={locale}/> : label(locale,'Not specified','未注明')}</dd></div>
      <div><dt>{label(locale,'Source time zone','来源时区')}</dt><dd>{source.timezone}</dd></div>
    </dl>
  </li>;
}

function Timeline({items,locale,query,projects,detail}: {
  items: TrackerMilestoneView[], locale: Locale, query: string, projects: Map<string,TrackerProjectView>, detail: boolean,
}) {
  return <section className="tracker-timeline" aria-labelledby="tracker-timeline-title">
    <div className="section-heading"><h2 id="tracker-timeline-title">{label(locale,'Milestone timeline','里程碑时间线')}</h2></div>
    {items.length ? <ol className="tracker-milestones">
      {items.map(item => {
        const project = projects.get(item.projectId);
        return <li key={item.id} className="tracker-milestone">
          <div className="tracker-milestone-date">
            <span>{item.eventAt ? label(locale,'Event date','事件日期') : label(locale,'Publication date','发布日期')}</span>
            <Day value={item.eventAt ?? item.publishedAt} locale={locale}/>
            {item.eventAt && <span>{label(locale,'Published','发布于')} <Day value={item.publishedAt} locale={locale}/></span>}
            {!item.eventAt && <span>{label(locale,'Event date unavailable','未注明事件日期')}</span>}
          </div>
          <article className="tracker-milestone-content">
            <div className="tracker-evidence-labels">
              <span className="stage">{stages[item.stage][locale]}</span>
              <span className="tracker-evidence-status" data-status={item.status}>{statuses[item.status][locale]}</span>
            </div>
            <h3>{item.title[locale]}</h3>
            {!detail && project && <Link className="tracker-project-reference" href={trackerPath(locale,'projects',project.id)}>{project.name[locale]} <span aria-hidden="true">↗</span></Link>}
            <p>{item.summary[locale]}</p>
            <details className="tracker-references">
              <summary>{label(locale,'Evidence references','证据引用')} ({item.sources.length})</summary>
              <ul>{item.sources.map(source => <Reference key={source.id} source={source} locale={locale}/>)}</ul>
              <Link className="text-link" href={`/${locale}/digest/${encodeURIComponent(item.issueSlug)}/sources`}>
                {label(locale,'Edition source notebook','期刊来源笔记')} <span aria-hidden="true">↗</span>
              </Link>
            </details>
          </article>
        </li>;
      })}
    </ol> : <div className="empty">
      <h3>{query ? label(locale,'No matching milestones.','没有与搜索匹配的里程碑。') : label(locale,'No public milestones yet.','暂无公开里程碑。')}</h3>
      <p>{query ? label(locale,'Try a broader keyword.','请尝试更宽泛的关键词。') : label(locale,'Milestones appear after their editorial content and sources are cleared for public display.','编辑内容和来源获准公开展示后，将显示相应的里程碑。')}</p>
    </div>}
  </section>;
}

function Directory({section,entries,locale}: {section: TrackerSection, entries: TrackerTopic[], locale: Locale}) {
  return <ul className="tracker-directory">
    {entries.map(entry => <li key={entry.id}><Link href={trackerPath(locale,section,entry.id)}>{entry.name[locale]} <span aria-hidden="true">↗</span></Link></li>)}
  </ul>;
}

function ProjectTopics({data,project,locale}: {data: TrackerData, project: TrackerProjectView, locale: Locale}) {
  const companies = data.companies.filter(company => project.companyIds.includes(company.id));
  const technologies = data.technologies.filter(technology => project.technologyIds.includes(technology.id));
  if (!companies.length && !technologies.length) return null;
  return <dl className="tracker-topic-links">
    {companies.length > 0 && <div><dt>{label(locale,'Companies','企业')}</dt><dd><Directory entries={companies} section="companies" locale={locale}/></dd></div>}
    {technologies.length > 0 && <div><dt>{label(locale,'Technologies','技术')}</dt><dd><Directory entries={technologies} section="technologies" locale={locale}/></dd></div>}
  </dl>;
}

export async function Tracker({locale,path,query}: {locale: Locale, path: string[], query?: string | string[]}) {
  const {data,section,entry} = await resolveTrackerPage(path);
  const q = typeof query === 'string' ? query.trim().slice(0, 160) : '';
  const terms = q ? normalize(q).split(' ') : [];
  const projects = new Map(data.projects.map(project => [project.id, project]));
  const companies = new Map(data.companies.map(company => [company.id, company]));
  const technologies = new Map(data.technologies.map(technology => [technology.id, technology]));
  const scope = data.milestones.filter(item => {
    if (section === 'companies') return entry ? item.companyIds.includes(entry.id) : item.companyIds.length > 0;
    if (section === 'technologies') return entry ? item.technologyIds.includes(entry.id) : item.technologyIds.length > 0;
    return !entry || item.projectId === entry.id;
  });
  const items = scope.filter(item => {
    if (!terms.length) return true;
    const topics = [projects.get(item.projectId), ...item.companyIds.map(id => companies.get(id)), ...item.technologyIds.map(id => technologies.get(id))];
    return contains([
      item.title.en, item.title.zh, item.summary.en, item.summary.zh,
      stages[item.stage].en, stages[item.stage].zh, statuses[item.status].en, statuses[item.status].zh,
      ...topics.flatMap(topic => topic ? [topic.name.en, topic.name.zh] : []),
      ...item.sources.map(source => source.name),
    ], terms);
  });
  const project = section === 'projects' && entry ? projects.get(entry.id) : undefined;
  const directory = section && !entry ? data[section].filter(item => nameMatches(item, terms)) : undefined;
  const title = entry?.name[locale] ?? trackerCopy[section ?? 'overview'][locale];

  return <main className="page tracker" id="main">
    <header className="page-heading">
      <Link className="back-link" href={section ? trackerPath(locale, entry ? section : undefined) : `/${locale}`}>
        <span aria-hidden="true">← </span>{entry && section ? trackerCopy[section][locale] : section ? trackerCopy.overview[locale] : label(locale,'Back to the digest','返回简报')}
      </Link>
      <h1>{title}</h1>
      {!entry && <p>{trackerDescription(locale,section)}</p>}
    </header>
    {data.synthetic && <p className="tracker-demo">{label(locale,'Demonstration data. The projects and milestones shown here are synthetic.','演示数据。此处展示的项目与里程碑均为模拟内容。')}</p>}
    {!section && <nav className="tracker-sections" aria-label={label(locale,'Tracker modules','追踪模块')}>
      {trackerSections.map(key => <Link key={key} href={trackerPath(locale,key)}>{trackerCopy[key][locale]} <span aria-hidden="true">↗</span></Link>)}
    </nav>}
    {project && <ProjectTopics data={data} project={project} locale={locale}/>}
    <form className="search-form tracker-search" action={trackerPath(locale, section, entry?.id)}>
      <label htmlFor="tracker-query">{label(locale,'Search this tracker page','搜索此追踪页面')}</label>
      <div className="search-input">
        <input id="tracker-query" type="search" name="q" maxLength={160} defaultValue={q} placeholder={label(locale,'Name, milestone or stage','名称、里程碑或阶段')}/>
        <button type="submit">{label(locale,'Search','搜索')}</button>
      </div>
    </form>
    {directory && section && <section className="tracker-directory-section" aria-labelledby="tracker-directory-title">
      <div className="section-heading"><h2 id="tracker-directory-title">{label(locale,'Directory','目录')}</h2></div>
      {directory.length ? <Directory section={section} entries={directory} locale={locale}/> : <p className="muted">{q ? label(locale,'No matching entries.','没有匹配的条目。') : label(locale,'No public entries yet.','暂无公开条目。')}</p>}
    </section>}
    {!section && q && trackerSections.map(key => {
      const entries = data[key].filter(item => nameMatches(item, terms));
      return entries.length > 0 && <section key={key} className="tracker-directory-section"><div className="section-heading"><h2>{trackerCopy[key][locale]}</h2></div><Directory section={key} entries={entries} locale={locale}/></section>;
    })}
    <Timeline items={items} locale={locale} query={q} projects={projects} detail={Boolean(project)}/>
  </main>;
}
