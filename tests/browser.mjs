// Run against a disposable Chrome started with --remote-debugging-port=9228.
// Uses Node 22+ built-ins; no browser test dependencies are needed.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
const debug = process.env.CDP_URL || 'http://127.0.0.1:9228';
const base = process.env.SCOUT_URL || 'http://127.0.0.1:8765';
const root = path.resolve(import.meta.dirname,'..');
const version = await (await fetch(debug+'/json/version')).json();
const ws = new WebSocket(version.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
let sequence=0;const pending=new Map();const events=[];
ws.onmessage=e=>{const msg=JSON.parse(e.data);if(msg.id){const s=pending.get(msg.id);pending.delete(msg.id);if(msg.error)s?.reject(new Error(JSON.stringify(msg.error)));else s?.resolve(msg.result);}else {events.push(msg);if(msg.method==='Fetch.requestPaused'&&msg.sessionId){const html='<html><head><title>Isolated FACEIT match fixture</title></head><body style="background:#10131a;color:#ddd;font-family:Arial;padding:40px"><h1>Isolated matchroom fixture</h1><p>Synthetic integration test. No real FACEIT page or account.</p></body></html>';cdp('Fetch.fulfillRequest',{requestId:msg.params.requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'text/html'}],body:Buffer.from(html).toString('base64')},msg.sessionId).catch(console.error);}}};
function cdp(method,params={},sessionId){return new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}));});}
const {targetId}=await cdp('Target.createTarget',{url:'about:blank'});
const {sessionId}=await cdp('Target.attachToTarget',{targetId,flatten:true});
await cdp('Page.enable',{},sessionId);await cdp('Runtime.enable',{},sessionId);
const evalJS=async expression=>{const result=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true},sessionId);if(result.exceptionDetails)throw new Error(result.exceptionDetails.text);return result.result.value;};
const wait=ms=>new Promise(r=>setTimeout(r,ms));
try{
  await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false},sessionId);
  await cdp('Page.navigate',{url:base+'/preview'},sessionId);
  for(let i=0;i<50;i++){if(await evalJS('document.querySelectorAll(".scout-player").length')===5)break;await wait(100);}
  assert.equal(await evalJS('document.querySelectorAll(".scout-player").length'),5);
  assert.match(await evalJS('document.querySelector(".scout-preview-banner").textContent'),/SYNTHETIC/);
  assert.match(await evalJS('document.querySelector(".scout-priority h3").textContent'),/B is worth testing/);
  assert.equal(await evalJS('document.documentElement.scrollWidth<=innerWidth'),true);
  await fs.mkdir(path.join(root,'..','work','qa'),{recursive:true});
  const screenshot=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false},sessionId);
  await fs.writeFile(path.join(root,'..','work','qa','site-scout-desktop.png'),Buffer.from(screenshot.data,'base64'));
  await evalJS(`(async()=>{const job=await(await fetch('/api/example')).json();job.brief.players[0].nickname='<img src=x onerror=window.__xss=1>';view.render(job);})()`);
  assert.equal(await evalJS('document.querySelectorAll(".scout-shell img").length'),0);
  assert.equal(await evalJS('window.__xss===undefined'),true);
  assert.match(await evalJS('document.querySelector(".scout-shell").textContent'),/<img src=x/);
  await evalJS('preview()');await wait(150);
  await cdp('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true},sessionId);
  assert.equal(await evalJS('document.documentElement.scrollWidth<=innerWidth'),true);
  const mobile=await cdp('Page.captureScreenshot',{format:'png'},sessionId);
  await fs.writeFile(path.join(root,'..','work','qa','site-scout-mobile.png'),Buffer.from(mobile.data,'base64'));
  const exceptions=events.filter(e=>e.method==='Runtime.exceptionThrown');
  assert.equal(exceptions.length,0,JSON.stringify(exceptions));
  console.log('PASS: desktop render, synthetic labels, five-player report, site evidence, nickname escaping and mobile overflow.');
  const loaded=await cdp('Extensions.loadUnpacked',{path:path.join(root,'extension')});
  console.log('Extension loaded in disposable Chrome:',loaded.id);
  if(process.env.SCOUT_FIXTURE_CONFIG){
    const {token}=JSON.parse(await fs.readFile(process.env.SCOUT_FIXTURE_CONFIG,'utf8'));
    await cdp('Page.navigate',{url:'chrome-extension://'+loaded.id+'/dashboard.html'},sessionId);await wait(500);
    await evalJS('chrome.storage.local.set({localToken:'+JSON.stringify(token)+'})');
    await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false},sessionId);
    await cdp('Fetch.enable',{patterns:[{urlPattern:'https://www.faceit.com/*',requestStage:'Request'}]},sessionId);
    await cdp('Page.navigate',{url:'https://www.faceit.com/en/cs2/room/1-11111111-2222-4333-8444-555555555555'},sessionId);
    for(let i=0;i<80;i++){if(await evalJS('document.getElementById("site-scout-extension-root")?.shadowRoot.querySelectorAll(".scout-player").length')===5)break;await wait(100);}
    assert.equal(await evalJS('document.getElementById("site-scout-extension-root")?.shadowRoot.querySelectorAll(".scout-player").length'),5);
    assert.match(await evalJS('document.getElementById("site-scout-extension-root").shadowRoot.querySelector(".scout-preview-banner").textContent'),/SYNTHETIC/);
    const matchShot=await cdp('Page.captureScreenshot',{format:'png'},sessionId);
    await fs.writeFile(path.join(root,'..','work','qa','site-scout-matchroom.png'),Buffer.from(matchShot.data,'base64'));
    await evalJS('history.pushState({},"","/en/home")');await wait(1200);
    assert.equal(await evalJS('document.getElementById("site-scout-extension-root")===null'),true);
    console.log('PASS: actual MV3 service worker, automatic matchroom injection, paired localhost calls, five-player briefing and SPA cleanup.');
  }
}finally{await cdp('Target.closeTarget',{targetId});ws.close();}
