import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createRequire} from 'node:module';
import path from 'node:path';
import {test} from 'node:test';
import {fileURLToPath} from 'node:url';
import vm from 'node:vm';
import ts from 'typescript';

const shared = fileURLToPath(new URL('../../../packages/shared/', import.meta.url));
const loaded = new Map();

function load(filename) {
  if (loaded.has(filename)) return loaded.get(filename);
  const nativeRequire = createRequire(filename);
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true},
  }).outputText;
  vm.runInNewContext(code, {
    exports, URL, Date,
    require: name => name.startsWith('.') && !name.endsWith('.json')
      ? load(path.resolve(path.dirname(filename), name + '.ts')) : nativeRequire(name),
  }, {filename});
  loaded.set(filename, exports);
  return exports;
}

const {canonicalIssueHash} = load(path.join(shared, 'public-display.ts'));
const {projectTrackerMilestone, projectTrackerFixtures, trackerData} = load(path.join(shared, 'tracker/projection.ts'));
const fixtures = JSON.parse(fs.readFileSync(path.join(shared, 'fixtures/issues.json'), 'utf8'));
const project = 'project-' + 'a'.repeat(24);
const milestone = 'milestone-' + 'b'.repeat(24);
const serial = value => JSON.parse(JSON.stringify(value));

function scenario() {
  const content = structuredClone(fixtures[0]);
  content.id = 'qa-tracker-shape';
  content.slug = 'qa-tracker-shape';
  content.synthetic = false;
  content.privateEvidence = 'QA_PRIVATE_ISSUE';
  const story = content.stories[0];
  content.stories = [story];
  content.sources = content.sources.slice(0, 2);
  content.sources.forEach((source, index) => {
    Object.assign(source, {
      synthetic: false, name: `Publisher ${index}`, url: `https://publisher-${index}.test/entry`,
      publishedAt: `2026-01-0${index + 2}T10:00:00Z`, eventAt: '2026-01-01T09:00:00Z',
      privateEvidence: 'QA_PRIVATE_SOURCE', excerpt: {en: 'QA_PRIVATE_EN', zh: 'QA_PRIVATE_ZH'},
    });
  });
  Object.assign(story, {
    company: 'Siemens', category: 'Digital Twins & Simulation', evidenceStatus: 'verified',
    title: {en: 'Test: Siemens digital twin', zh: '测试：西门子数字孪生'},
    sourceIds: content.sources.map(source => source.id), privateEvidence: 'QA_PRIVATE_STORY',
  });
  const issueHash = canonicalIssueHash(content);
  const revision = {
    issue: {id: content.id, slug: content.slug, state: 'published', validated: true, content},
    issueHash, storyId: story.id, stage: story.maturity, withdrawn: false,
    evidence: content.sources.map(source => ({
      sourceKey: source.id, publisher: source.name, canonicalUrl: source.url, kind: 'vendor',
      publishedAt: new Date(source.publishedAt), eventAt: new Date(source.eventAt), sourceTimezone: source.timezone,
      rawArticleId: 'QA_PRIVATE_CANONICAL_ID',
    })),
    companies: [{companyId: 'siemens'}, {companyId: 'nvidia'}],
    technologies: [{technologyId: 'digital-twins'}, {technologyId: 'industrial-agents'}],
  };
  return {revision, policy: reviewFor(content)};
}

function reviewFor(content) {
  return {version: 1, intendedUse: 'public-web', editions: [{
    issueId: content.id, contentSha256: canonicalIssueHash(content), editorialApproved: true,
    reviewedBy: 'Fixture reviewer', reviewedAt: '2026-01-01', reviewEvidence: 'https://review.test/QA_PRIVATE_ENTRY',
    sourceLinks: content.sources.map(source => ({
      sourceId: source.id, url: source.url, publisher: source.name, approved: true, basis: 'legal-review',
      evidenceUrl: 'https://review.test/QA_PRIVATE_PERMISSION', reviewedBy: 'Fixture reviewer', reviewedAt: '2026-01-01',
    })),
  }]};
}

test('tracker projects only approved bilingual prose, supported topics and canonical citations', () => {
  const {revision, policy} = scenario();
  const allowed = projectTrackerMilestone(milestone, project, revision, policy);
  assert.ok(allowed);
  assert.equal(allowed.status, 'vendor_claim');
  assert.equal(allowed.eventAt, '2026-01-01T09:00:00.000Z');
  assert.equal(allowed.publishedAt, '2026-01-02T10:00:00.000Z');
  assert.equal(allowed.sources[0].publishedAt, '2026-01-02T10:00:00Z');
  assert.equal(allowed.sources[0].name, 'Publisher 0');
  assert.equal(allowed.sources[0].url, 'https://publisher-0.test/entry');
  assert.equal(allowed.title.zh, '测试：西门子数字孪生');
  assert.deepEqual(serial(allowed.companyIds), ['siemens']);
  assert.deepEqual(serial(allowed.technologyIds), ['digital-twins']);
  assert.doesNotMatch(JSON.stringify(allowed), /QA_PRIVATE|"excerpt"|issueHash|rawArticleId/);
});

test('tracker requires the current published issue, exact revision and complete public clearance', () => {
  for (const mutate of [
    (r, p) => p.editions.pop(),
    (r, p) => { p.editions[0].editorialApproved = false; },
    (r, p) => { p.editions[0].sourceLinks[0].approved = false; },
    r => { r.issue.content.privateEvidence = 'changed'; },
    r => { r.issueHash = '0'.repeat(64); },
    r => { r.issue.slug = 'changed'; },
    r => { r.issue.state = 'draft'; },
    r => { r.issue.validated = false; },
    r => { r.storyId = 'unknown'; },
    r => { r.stage = 'commercial'; },
    r => { r.withdrawn = true; },
    r => r.evidence.pop(),
    r => { r.evidence[1].sourceKey = r.evidence[0].sourceKey; },
    r => { r.evidence[0].canonicalUrl += '?different=1'; },
    r => { r.evidence[0].publisher += ' altered'; },
    r => { r.evidence[0].kind = 'unsupported-role'; },
    r => { r.evidence[0].publishedAt = new Date(0); },
    r => { r.evidence[0].eventAt = null; },
    r => { r.evidence[0].sourceTimezone += ' altered'; },
  ]) {
    const {revision, policy} = scenario();
    mutate(revision, policy);
    assert.equal(projectTrackerMilestone(milestone, project, revision, policy), null, mutate.toString());
  }
  const {revision, policy} = scenario();
  assert.equal(projectTrackerMilestone(milestone, 'uncleared-project-key', revision, policy), null);
});

test('independent status requires distinct attributed publishers and domains', () => {
  for (const [expected, publisher, host, role] of [
    ['independently_verified', null, null, 'independent'],
    ['reported', 'Publisher 0', null, 'independent'],
    ['reported', null, 'www.publisher-0.test', 'independent'],
    ['reported', null, null, 'other'],
  ]) {
    const {revision} = scenario();
    const {content} = revision.issue;
    const second = content.sources[1];
    if (publisher) second.name = publisher;
    if (host) second.url = `https://${host}/second`;
    revision.evidence[0].kind = 'independent';
    Object.assign(revision.evidence[1], {kind: role, publisher: second.name, canonicalUrl: second.url});
    revision.issueHash = canonicalIssueHash(content);
    assert.equal(projectTrackerMilestone(milestone, project, revision, reviewFor(content))?.status, expected);
  }
});

test('conflicting event dates remain unknown and fixtures never project real records', () => {
  const {revision} = scenario();
  const {content} = revision.issue;
  content.sources[1].eventAt = '2026-01-02T09:00:00Z';
  revision.evidence[1].eventAt = new Date(content.sources[1].eventAt);
  revision.issueHash = canonicalIssueHash(content);
  const allowed = projectTrackerMilestone(milestone, project, revision, reviewFor(content));
  assert.equal(allowed.eventAt, null);
  assert.notEqual(allowed.sources[0].eventAt, allowed.sources[1].eventAt);
  const hidden = trackerData([]);
  assert.equal(hidden.projects.length, 0);
  assert.equal(hidden.milestones.length, 0);
  assert.ok(hidden.companies.some(company => company.id === 'siemens'));
  const demo = projectTrackerFixtures([...fixtures, content]);
  assert.ok(demo.milestones.length > 0);
  assert.ok(demo.milestones.every(entry => entry.status === 'synthetic' && entry.sources.every(source => source.synthetic)));
  assert.doesNotMatch(JSON.stringify(demo), /QA_PRIVATE/);
  const dates = serial(demo.milestones.map(entry => entry.eventAt ?? entry.publishedAt));
  assert.deepEqual(dates, [...dates].sort().reverse());
});
