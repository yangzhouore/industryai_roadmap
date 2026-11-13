import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';

// Portable repository QA through an installed Chromium browser. No downloads,
// credentials, browser extensions, or native desktop automation are involved.
const base=new URL(process.env.WEB_URL||process.env.WEB_BASE_URL||'http://127.0.0.1:3000');
const output=process.env.BROWSER_ARTIFACTS_DIR?path.resolve(process.env.BROWSER_ARTIFACTS_DIR):path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../../artifacts/browser');
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
await fs.mkdir(output,{recursive:true});
const profile=await fs.mkdtemp(path.join(output,'profile-'));
const candidates=[process.env.CHROME_PATH,process.env.BROWSER_EXECUTABLE,'C:/Program Files/Google/Chrome/Application/chrome.exe','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','/usr/bin/chromium','/usr/bin/chromium-browser','/usr/bin/google-chrome','/opt/google/chrome/chrome'].filter(Boolean);
let executable;
for(const candidate of candidates){try{await fs.access(candidate);executable=candidate;break;}catch{}}
if(!executable)throw new Error('No installed Chromium executable. Set BROWSER_EXECUTABLE; this test does not download browsers.');
const browser=spawn(executable,['--headless=new','--remote-debugging-port=0','--remote-debugging-address=127.0.0.1',`--user-data-dir=${profile}`,'--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-extensions','--force-color-profile=srgb','about:blank'],{windowsHide:true,stdio:['ignore','ignore','pipe']});
let browserErrors='';browser.stderr.on('data',data=>{browserErrors+=data.toString();});
let ws;let id=0;const requests=new Map();const checks=[];const links=new Set();const screenshots=[];
const check=(name,condition,detail='')=>{checks.push({name,passed:Boolean(condition),detail});assert.ok(condition,`${name}: ${detail}`);};
function command(method,params={}){return new Promise((resolve,reject)=>{const requestId=++id;const timer=setTimeout(()=>{requests.delete(requestId);reject(new Error(`CDP timeout: ${method}`));},20000);requests.set(requestId,{resolve,reject,timer});ws.send(JSON.stringify({id:requestId,method,params}));});}
async function evaluate(expression){const result=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true,userGesture:true});if(result.exceptionDetails)throw new Error(result.exceptionDetails.text+': '+JSON.stringify(result.exceptionDetails.exception));return result.result.value;}
async function until(expression){for(let n=0;n<100;n++){if(await evaluate(expression))return;await sleep(100);}throw new Error('Browser readiness timeout: '+expression);}
async function navigate(route){const result=await command('Page.navigate',{url:new URL(route,base).href});assert.ok(!result.errorText,result.errorText);await until(`document.readyState==='complete'&&document.querySelector('main')&&!document.querySelector('main[aria-busy="true"]')&&location.pathname===${JSON.stringify(new URL(route,base).pathname)}`);await sleep(250);}
async function viewport(width,height){await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<700});}
async function screenshot(name){const metrics=await command('Page.getLayoutMetrics');const size=metrics.cssContentSize||metrics.contentSize;const shot=await command('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,clip:{x:0,y:0,width:Math.ceil(size.width),height:Math.ceil(size.height),scale:1}});const filename=path.join(output,name+'.png');await fs.writeFile(filename,Buffer.from(shot.data,'base64'));screenshots.push(filename);}
async function audit(name,locale){
  const result=await evaluate(`(()=>{
    const root=document.querySelector('.shell');const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none';};
    const controls=[...root.querySelectorAll('a[href],button,input:not([type=hidden]),select,textarea,[role=button]')].filter(visible);
    const accessibleName=e=>e.getAttribute('aria-label')||(e.getAttribute('aria-labelledby')||'').split(/\\s+/).map(id=>document.getElementById(id)?.textContent||'').join(' ').trim()||[...(e.labels||[])].map(l=>l.textContent).join(' ').trim()||e.textContent.trim()||e.getAttribute('alt')||e.getAttribute('title')||e.value;
    const unnamed=controls.filter(e=>!accessibleName(e)).map(e=>e.outerHTML.slice(0,180));
    const ids=[...document.querySelectorAll('[id]')].map(e=>e.id);const duplicates=ids.filter((id,index)=>ids.indexOf(id)!==index);
    const headings=[...root.querySelectorAll('h1,h2,h3,h4,h5,h6')].filter(visible).map(e=>Number(e.tagName.slice(1)));const skips=headings.slice(1).filter((level,index)=>level>headings[index]+1);
    const imageNames=[...root.querySelectorAll('img,[role=img]')].filter(visible).every(e=>e.getAttribute('alt')!==null||Boolean(e.getAttribute('aria-label')));
    const rgb=s=>{const m=s.match(/^rgba?\\(([^)]+)\\)$/);if(!m)return null;const v=m[1].split(',').map(Number);return [v[0]/255,v[1]/255,v[2]/255,v.length>3?v[3]:1];};
    const mix=(fg,bg)=>[0,1,2].map(i=>fg[i]*fg[3]+bg[i]*(1-fg[3]));const luminance=c=>c.map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
    const background=e=>{const chain=[];for(let p=e;p;p=p.parentElement)chain.unshift(p);let result=[1,1,1];for(const item of chain){const c=rgb(getComputedStyle(item).backgroundColor);if(c)result=mix(c,result);}return result;};
    const contrast=[];const walk=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let node;while((node=walk.nextNode())){const e=node.parentElement;if(!node.textContent.trim()||!visible(e)||e.closest('[aria-hidden=true],[role=img],script,style'))continue;const style=getComputedStyle(e),fg=rgb(style.color);if(!fg)continue;const bg=background(e);const l1=luminance(mix(fg,bg)),l2=luminance(bg);const ratio=(Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05);const size=parseFloat(style.fontSize),large=size>=24||(size>=18.66&&Number(style.fontWeight)>=700),required=large?3:4.5;if(ratio+.01<required)contrast.push({text:node.textContent.trim().slice(0,65),ratio:Math.round(ratio*100)/100,required,color:style.color,background:bg,selector:e.className});}
    return {lang:document.documentElement.lang,mains:root.querySelectorAll('main').length,h1s:root.querySelectorAll('h1').length,unnamed,duplicates,skips,imageNames,overflow:document.documentElement.scrollWidth>innerWidth+1,width:innerWidth,scrollWidth:document.documentElement.scrollWidth,contrast,hrefs:[...root.querySelectorAll('a[href]')].map(a=>a.href)};
  })()`);
  check(name+' language',result.lang===locale,result.lang);
  check(name+' landmark and primary heading',result.mains===1&&result.h1s===1,JSON.stringify({mains:result.mains,h1s:result.h1s}));
  check(name+' named interactive controls',result.unnamed.length===0,JSON.stringify(result.unnamed));
  check(name+' unique IDs',result.duplicates.length===0,JSON.stringify(result.duplicates));
  check(name+' heading hierarchy',result.skips.length===0,JSON.stringify(result.skips));
  check(name+' graphic alternatives',result.imageNames);
  check(name+' no horizontal overflow',!result.overflow,JSON.stringify({viewport:result.width,content:result.scrollWidth}));
  check(name+' text contrast',result.contrast.length===0,JSON.stringify(result.contrast));
  const tree=await command('Accessibility.getFullAXTree');
  check(name+' accessibility tree main',tree.nodes.some(n=>!n.ignored&&n.role?.value==='main'));
  check(name+' named accessibility navigation',tree.nodes.some(n=>!n.ignored&&n.role?.value==='navigation'&&Boolean(n.name?.value)));
  for(const href of result.hrefs){const url=new URL(href);if(url.origin===base.origin){url.hash='';links.add(url.href);}}
}
try{
  let activePort;for(let n=0;n<150;n++){try{activePort=await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8');break;}catch{if(browser.exitCode!==null)throw new Error('Browser exited: '+browserErrors);await sleep(100);}}
  if(!activePort)throw new Error('Browser debugging endpoint unavailable: '+browserErrors);
  const port=activePort.split('\n')[0];const target=await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'})).json();
  ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
  ws.addEventListener('message',event=>{const message=JSON.parse(event.data);const request=requests.get(message.id);if(!request)return;requests.delete(message.id);clearTimeout(request.timer);if(message.error)request.reject(new Error(JSON.stringify(message.error)));else request.resolve(message.result);});
  await command('Page.enable');await command('Runtime.enable');await command('Accessibility.enable');await command('Page.bringToFront');
  const cases=[['home-desktop','/en',1440,1000,'en'],['home-mobile','/en',375,812,'en'],['home-small-mobile','/en',320,720,'en'],['home-zh-mobile','/zh',375,812,'zh'],['digest-desktop','/en/digest/2026-11-12',1200,900,'en'],['sources-mobile','/zh/digest/2026-11-12/sources',375,812,'zh'],['search-mobile','/en/search?q=robot',375,812,'en']];
  for(const [name,route,width,height,locale] of cases){await viewport(width,height);await navigate(route);if(name==='home-desktop')check('browser target is explicit fixture server',await evaluate("Boolean(document.querySelector('.fixture-notice'))"),'Start this deterministic QA target with DATA_MODE=fixture.');await screenshot(name);await audit(name,locale);}
  await viewport(1200,900);await navigate('/en');await evaluate('document.activeElement?.blur()');
  await command('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});await command('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
  check('keyboard first focus is skip link',await evaluate("document.activeElement.classList.contains('skip-link')"));
  check('keyboard focus visible',await evaluate("getComputedStyle(document.activeElement).outlineStyle!=='none'&&parseFloat(getComputedStyle(document.activeElement).outlineWidth)>=2&&document.activeElement.getBoundingClientRect().top>=0"));
  await command('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});await command('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});await until("location.hash==='#main'");check('keyboard skip link targets content',await evaluate("location.hash==='#main'&&Boolean(document.getElementById('main'))"));
  for(const route of ['/en/search?q=robot&category=Robotics%20%26%20Physical%20AI&page=1','/en/digest/2026-11-12/sources']){await navigate(route);const before=new URL(route,base);await evaluate("document.querySelector('.language').click()");await until("location.pathname.startsWith('/zh/')&&document.documentElement.lang==='zh'");const after=new URL(await evaluate('location.href'));check('locale switch preserves route '+route,after.pathname===before.pathname.replace(/^\/en/,'/zh'));check('locale switch preserves query '+route,JSON.stringify([...after.searchParams].sort())===JSON.stringify([...before.searchParams].sort()));await evaluate("document.querySelector('.language').click()");await until("location.pathname.startsWith('/en/')&&document.documentElement.lang==='en'");}
  for(const href of links){const response=await fetch(href);check('navigation '+new URL(href).pathname,response.status===200,String(response.status));}
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({browser:executable,base:base.href,checks,screenshots},null,2));
  console.log(`${checks.length} browser checks passed. Screenshots: ${output}`);
}catch(error){await fs.writeFile(path.join(output,'report.json'),JSON.stringify({browser:executable,base:base.href,checks,screenshots,error:String(error)},null,2));throw error;}
finally{
  if(ws?.readyState===WebSocket.OPEN){try{await command('Browser.close');}catch{}ws.close();}
  if(browser.exitCode===null){await Promise.race([new Promise(resolve=>browser.once('exit',resolve)),sleep(3000)]);if(browser.exitCode===null)browser.kill();}
  for(const request of requests.values())clearTimeout(request.timer);
  // Remove only this test's resolved browser profile under its artifact folder.
  if(path.resolve(profile).startsWith(output+path.sep)){try{await fs.rm(profile,{recursive:true,force:true,maxRetries:3,retryDelay:200});}catch{console.warn('Browser profile cleanup deferred:',profile);}}
}
