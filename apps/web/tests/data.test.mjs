import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const __dirname=path.dirname(fileURLToPath(import.meta.url));
import ts from 'typescript';
const filename=path.resolve(__dirname,'../src/lib/data.ts');
const compiled=ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText;
function reader(env={},rows=[],policy={version:1,intendedUse:'public-web',editions:[]}){
  const exportsObject={};const queries=[];let disconnects=0;
  class PrismaClient{
    digestIssue={findMany:async query=>{queries.push(query);return rows;}};
    async $disconnect(){disconnects++;}
  }
  const originalRequire=createRequire(filename);
  const require=name=>name==='server-only'?{}:name.endsWith('/config/public-display.json')?policy:name==='@industrial/db'?{PrismaClient}:originalRequire(name);
  vm.runInNewContext(compiled,{exports:exportsObject,require,process:{env},URL,Intl,Date,Set});
  return {...exportsObject,queries,get disconnects(){return disconnects;}};
}
const {validIssue,getIssues}=reader({DATA_MODE:'fixture'});
const fixture=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../../../packages/shared/fixtures/issues.json'),'utf8'))[0];
function changed(fn){const value=structuredClone(fixture);fn(value);return value;}
test('fixture public reader exposes only published validated editions',async()=>{const issues=await getIssues();assert.equal(issues.length,3);assert.ok(issues.every(i=>i.state==='published'&&i.validated));assert.ok(issues.every(i=>i.sources.every(source=>!('excerpt' in source))));});
test('publication visibility rejects draft or unvalidated content',()=>{assert.equal(validIssue(changed(i=>i.state='draft')),false);assert.equal(validIssue(changed(i=>i.validated=false)),false);});
test('malformed database JSON fails closed without throwing',()=>{for(const bad of [null,{},[],{stories:[null]},changed(i=>i.stories=[null]),changed(i=>i.sources=[null]),changed(i=>i.stories[0].sourceIds=null)])assert.equal(validIssue(bad),false);});
test('unsupported citations and duplicate IDs cannot reach public readers',()=>{assert.equal(validIssue(changed(i=>i.stories[0].sourceIds=['missing'])),false);assert.equal(validIssue(changed(i=>i.sources.push(i.sources[0]))),false);assert.equal(validIssue(changed(i=>i.stories.push(i.stories[0]))),false);});
test('synthetic content cannot lose its fixture status',()=>{assert.equal(validIssue(changed(i=>i.synthetic=false)),false);assert.equal(validIssue(changed(i=>i.sources[0].synthetic=false)),false);assert.equal(validIssue(changed(i=>i.stories[0].evidenceStatus='verified')),false);});
test('unsafe links and fake fixture URLs are rejected',()=>{for(const url of ['javascript:alert(1)','http://example.org/fixtures/a','https://user:secret@example.org/fixtures/a','https://unrelated.test/fixtures/a'])assert.equal(validIssue(changed(i=>i.sources[0].url=url)),false);});
test('bilingual parity, score bounds and maturity are enforced',()=>{assert.equal(validIssue(changed(i=>i.stories[0].title.zh='')),false);assert.equal(validIssue(changed(i=>i.stories[0].score=Infinity)),false);assert.equal(validIssue(changed(i=>i.stories[0].score=101)),false);assert.equal(validIssue(changed(i=>i.stories[0].maturity='imagined')),false);});
function realIssue(){return changed(issue=>{
  issue.id='test-real-shape';issue.slug='test-real-shape';issue.synthetic=false;
  issue.sources.forEach((source,index)=>{source.synthetic=false;source.url=`https://source.test/article-${index}`;});
  issue.stories.forEach(story=>{story.evidenceStatus='verified';});
});}
test('default reader uses database and excludes synthetic issues, stories and sources',async()=>{
  const real=realIssue();
  const syntheticStory=structuredClone(real);syntheticStory.stories[0].synthetic=true;
  const syntheticEvidence=structuredClone(real);syntheticEvidence.stories[0].evidenceStatus='synthetic';
  const syntheticSource=structuredClone(real);syntheticSource.sources[0].synthetic=true;
  const missingFlag=structuredClone(real);delete missingFlag.synthetic;
  const draft=structuredClone(real);draft.state='draft';
  const unvalidated=structuredClone(real);unvalidated.validated=false;
  const dbReader=reader({},[real,fixture,syntheticStory,syntheticEvidence,syntheticSource,missingFlag,draft,unvalidated,null].map(content=>({content})),approval(real));
  const issues=await dbReader.getIssues();
  assert.equal(issues.length,1);assert.equal(issues[0].id,real.id);
  assert.equal(dbReader.queries.length,1);assert.equal(dbReader.disconnects,1);
  assert.deepEqual(JSON.parse(JSON.stringify(dbReader.queries[0].where)),{state:'published',validated:true,content:{path:['synthetic'],equals:false}});
});
test('database default never substitutes fixtures for an empty publication set',async()=>{
  const dbReader=reader();assert.equal((await dbReader.getIssues()).length,0);assert.equal(dbReader.queries.length,1);
  const fixtureReader=reader({DATA_MODE:'fixture'});assert.equal((await fixtureReader.getIssues()).length,3);assert.equal(fixtureReader.queries.length,0);
  const typoReader=reader({DATA_MODE:'fixtures'});assert.equal((await typoReader.getIssues()).length,0);assert.equal(typoReader.queries.length,1);
});

function approval(issue){
  return {version:1,intendedUse:'public-web',editions:[{
    issueId:issue.id,contentSha256:reader().canonicalIssueHash(issue),editorialApproved:true,
    reviewedBy:'Human editorial reviewer',reviewedAt:'2026-01-01',reviewEvidence:'https://review.test/editorial/approved',
    sourceLinks:issue.sources.map(source=>({sourceId:source.id,url:source.url,publisher:source.name,
      approved:true,basis:'legal-review',evidenceUrl:'https://review.test/source/permission',
      reviewedBy:'Human rights reviewer',reviewedAt:'2026-01-01'}))
  }]};
}
test('real content defaults to denied; runtime environment flags cannot bypass clearance',async()=>{
  const issue=realIssue();
  for(const env of [{},{PUBLIC_DISPLAY_APPROVED:'true'},{ALLOW_UNREVIEWED_NEWS:'true'},{DATA_MODE:'database'}]){
    const db=reader(env,[{content:issue}]);assert.equal((await db.getIssues()).length,0);
  }
});
test('approved real content is projected without excerpts, private fields, assets or nested aliases',async()=>{
  const issue=realIssue();
  issue.privateEvidence='private-issue-sentinel';issue.assets=['private-asset-sentinel'];
  issue.title.private='private-text-sentinel';issue.sources[0].privateEvidence='private-source-sentinel';
  issue.sources[0].excerpt={en:'private-excerpt-en-sentinel',zh:'private-excerpt-zh-sentinel'};
  issue.stories[0].review={secret:'private-story-sentinel'};
  issue.stories[0].summary.private='private-summary-sentinel';
  const storedBefore=JSON.stringify(issue);
  const db=reader({},[{content:issue}],approval(issue));
  const [projected]=await db.getIssues();assert.ok(projected);assert.equal(projected.id,issue.id);
  const output=JSON.stringify(projected);assert.doesNotMatch(output,/private-|"excerpt":|"assets":|"privateEvidence":|"review":/);
  assert.notEqual(projected.title,issue.title);assert.notEqual(projected.stories[0].summary,issue.stories[0].summary);
  assert.notEqual(projected.stories[0].sourceIds,issue.stories[0].sourceIds);assert.notEqual(projected.sources[0],issue.sources[0]);
  projected.stories[0].summary.en='changed projection';projected.stories[0].sourceIds.push('changed projection');
  assert.equal(JSON.stringify(issue),storedBefore);
  assert.notEqual(issue.stories[0].summary.en,'changed projection');assert.ok(!issue.stories[0].sourceIds.includes('changed projection'));
});
test('stale full-content hashes and missing editorial approval withhold the whole edition',async()=>{
  const issue=realIssue();const policy=approval(issue);
  for(const mutate of [i=>i.title.en+=' edited',i=>i.sources[0].excerpt.en+=' changed evidence',i=>i.review={new:'private'},i=>i.stories[0].score+=1]){
    const changedIssue=structuredClone(issue);mutate(changedIssue);
    assert.equal((await reader({},[{content:changedIssue}],policy).getIssues()).length,0);
  }
  const denied=structuredClone(policy);denied.editions[0].editorialApproved=false;
  assert.equal((await reader({},[{content:issue}],denied).getIssues()).length,0);
});
test('every exact source link and publisher requires complete explicit permission',async()=>{
  const issue=realIssue();
  for(const mutate of [p=>p.editions[0].sourceLinks.pop(),p=>p.editions[0].sourceLinks[0].approved=false,
    p=>p.editions[0].sourceLinks[0].url+='?different=1',p=>p.editions[0].sourceLinks[0].publisher+=' other',
    p=>p.editions[0].sourceLinks[0].sourceId='other',p=>delete p.editions[0].sourceLinks[0].basis,
    p=>p.editions[0].sourceLinks[0].basis='feed-available',p=>p.editions[0].sourceLinks[0].evidenceUrl='http://review.test',
    p=>p.editions[0].sourceLinks[0].reviewedBy='',p=>p.editions[0].sourceLinks[0].reviewedAt='2026-02-31',
    p=>p.editions[0].sourceLinks[0].reviewedAt='2999-01-01']){
    const policy=approval(issue);mutate(policy);
    assert.equal((await reader({},[{content:issue}],policy).getIssues()).length,0);
  }
});
test('malformed or duplicate review policies fail closed',async()=>{
  const issue=realIssue();
  for(const policy of [null,{},[],{version:2,intendedUse:'public-web',editions:[]},
    {version:1,intendedUse:'internal',editions:[]},
    ...[p=>p.editions.push(p.editions[0]),p=>p.editions[0].sourceLinks.push(p.editions[0].sourceLinks[0]),
      p=>p.editions[0].reviewEvidence='',p=>p.editions[0].reviewedBy='',p=>p.editions[0].contentSha256='bad',
      p=>p.editions.push(null)].map(mutate=>{const p=approval(issue);mutate(p);return p;})]){
    assert.equal((await reader({},[{content:issue}],policy).getIssues()).length,0);
  }
});
test('canonical review hash is key-order independent and covers private content',()=>{
  const {canonicalIssueHash}=reader();const issue=realIssue();
  const reverse=Object.fromEntries(Object.entries(issue).reverse());
  assert.equal(canonicalIssueHash(issue),canonicalIssueHash(reverse));
  assert.notEqual(canonicalIssueHash(issue),canonicalIssueHash({...issue,privateEvidence:'new'}));
  for(const bad of [{value:undefined},{value:Infinity},new Date(),Object.create({private:'inherited'})]){
    assert.throws(()=>canonicalIssueHash(bad));
  }
  const cyclic={};cyclic.self=cyclic;assert.throws(()=>canonicalIssueHash(cyclic));
});
test('fixture projections strip unknown nested fields and retained excerpts too',()=>{
  const issue=changed(i=>{i.title.extra='fixture-private';i.stories[0].sourceIds.extra='array-private';i.sources[0].extra='source-private';});
  // Custom array properties are not JSON and must fail closed, even in demo mode.
  assert.equal(reader().projectPublicIssue(issue,null,true),null);
  delete issue.stories[0].sourceIds.extra;
  const projected=reader().projectPublicIssue(issue,null,true);assert.ok(projected);
  assert.doesNotMatch(JSON.stringify(projected),/fixture-private|source-private|excerpt/);
});
