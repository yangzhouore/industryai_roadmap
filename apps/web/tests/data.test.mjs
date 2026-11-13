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
function reader(env={},rows=[]){
  const exportsObject={};const queries=[];let disconnects=0;
  class PrismaClient{
    digestIssue={findMany:async query=>{queries.push(query);return rows;}};
    async $disconnect(){disconnects++;}
  }
  const originalRequire=createRequire(filename);
  const require=name=>name==='@industrial/db'?{PrismaClient}:originalRequire(name);
  vm.runInNewContext(compiled,{exports:exportsObject,require,process:{env},URL,Intl,Date,Set});
  return {...exportsObject,queries,get disconnects(){return disconnects;}};
}
const {validIssue,getIssues}=reader({DATA_MODE:'fixture'});
const fixture=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../../../packages/shared/fixtures/issues.json'),'utf8'))[0];
function changed(fn){const value=structuredClone(fixture);fn(value);return value;}
test('fixture public reader exposes only published validated editions',async()=>{const issues=await getIssues();assert.equal(issues.length,3);assert.ok(issues.every(i=>i.state==='published'&&i.validated));assert.ok(issues.every(validIssue));});
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
  const dbReader=reader({},[real,fixture,syntheticStory,syntheticEvidence,syntheticSource,missingFlag,draft,unvalidated,null].map(content=>({content})));
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
