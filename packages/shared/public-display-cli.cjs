// Fixed local bridge: shares the web gate; accepts data only, never module paths or code.
'use strict';
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {createRequire}=require('node:module');
const ts=require('typescript');
const filename=path.join(__dirname,'public-display.ts');
const compiled=ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const exportsObject={};
vm.runInNewContext(compiled,{exports:exportsObject,require:createRequire(filename),URL,Date,Set});
function execute(request){
  if(!request||typeof request!=='object'||Array.isArray(request))throw new Error('Invalid request');
  if(request.action==='hash')return {hash:exportsObject.canonicalIssueHash(request.issue)};
  if(request.action==='validate')return {valid:exportsObject.validIssue(request.issue)};
  if(request.action==='project')return {issue:exportsObject.projectPublicIssue(request.issue,request.policy,false)};
  throw new Error('Unsupported action');
}
module.exports={execute};
if(require.main===module){
  let input='';let size=0;
  process.stdin.setEncoding('utf8');
  process.stdin.on('data',chunk=>{
    size+=Buffer.byteLength(chunk,'utf8');
    if(size>8*1024*1024){process.stderr.write('Public-display request rejected.\n');process.exit(1);}
    input+=chunk;
  });
  process.stdin.on('end',()=>{
    try{process.stdout.write(JSON.stringify(execute(JSON.parse(input)))+'\n');}
    catch{process.stderr.write('Public-display request rejected.\n');process.exitCode=1;}
  });
}
