'use strict';
const extensionPage=location.protocol==='chrome-extension:';
const base=extensionPage?'http://127.0.0.1:8765':'';
const $=id=>document.getElementById(id);
let token='',generation=0,teamId='',lastStatus=null;
const view=SiteScout.mount($('briefing'),{onChooseTeam:id=>{teamId=id;scout();}});
function message(id,text,error=false){$(id).textContent=text;$(id).classList.toggle('error',error);}
async function api(path,method='GET',body,raw=false){
  const response=await fetch(base+path,{method,headers:{'Authorization':'Bearer '+token,...(!raw?{'Content-Type':'application/json'}:{})},...(method==='POST'?{body:raw?body:JSON.stringify(body)}:{})});
  const data=await response.json();if(!response.ok)throw new Error(data.error||'Local helper error.');return data;
}
async function persistToken(){
  if(extensionPage)await chrome.storage.local.set({localToken:token});else localStorage.setItem('siteScoutToken',token);
}
async function refreshStatus(){
  if(!token)return;
  try{
    const status=await api('/api/status');lastStatus=status;
    message('connectionStatus','Connected to local helper '+status.version+'.');
    $('demoCount').textContent=status.cache.demos;$('playerCount').textContent=status.cache.players;
    $('parserStatus').textContent=status.parser_available?'Demo parser installed. '+status.pending_demos+' cache tasks queued.':'Demo parser is not installed. Run the included demo-support installer to enable position analysis.';
    if(document.activeElement!==$('nickname')&&!$('nickname').dataset.edited)$('nickname').value=status.nickname||'';
    if(!$('autoDemos').dataset.edited)$('autoDemos').checked=status.auto_demos;
    if(!$('faceitKey').value)$('faceitKey').placeholder=status.configured?'A key is saved. Leave blank to keep it.':'Add a server-side Data API key';
    $('events').replaceChildren();for(const event of status.events.slice(0,5)){const row=document.createElement('li');const time=document.createElement('time');time.textContent=new Date(event.at*1000).toLocaleTimeString();row.append(time,document.createTextNode(event.message));$('events').append(row);}
  }catch(error){message('connectionStatus',error.message==='Failed to fetch'?'Start the helper on this computer, then connect.':error.message,true);}
}
async function preview(){
  generation++;$('previewTab').classList.add('active');$('liveTab').classList.remove('active');$('liveControls').hidden=true;
  try{const response=await fetch(base+'/api/example');view.render(await response.json());}catch{view.error('Start the local helper to load the example.');}
}
async function scout(){
  const current=++generation;
  $('scoutButton').disabled=true;message('scoutStatus','Retrieving available evidence...');view.status('Reading this matchroom...');
  try{
    let job=await api('/api/scout','POST',{match_id:$('matchLink').value,team_id:teamId,map:$('mapSelect').value||null});
    const started=Date.now();
    while(current===generation){
      view.render(job);if(job.team_id)teamId=job.team_id;
      if(job.status==='error'){message('scoutStatus',job.error,true);break;}
      if(job.status==='choose_team'){message('scoutStatus','Select your team in the briefing.');break;}
      message('scoutStatus',job.brief?'Briefing available. Checking for additional evidence...':'Retrieving available evidence...');
      if(Date.now()-started>90000)break;
      await new Promise(resolve=>setTimeout(resolve,job.brief?2500:700));if(current!==generation)break;
      if(job.status==='awaiting_map'&&Date.now()/1000-job.created_at>12){job=await api('/api/scout','POST',{match_id:$('matchLink').value,team_id:teamId,map:$('mapSelect').value||null});}
      else job=await api('/api/jobs/'+job.id);
    }
  }catch(error){if(current===generation){message('scoutStatus',error.message,true);view.error(error.message);}}
  finally{if(current===generation)$('scoutButton').disabled=false;}
}
$('pairButton').onclick=async()=>{token=$('pairToken').value.trim();await persistToken();refreshStatus();};
$('copyPair').onclick=async()=>{try{if(!token)throw new Error('Connect first.');await navigator.clipboard.writeText(token);message('connectionStatus','Pairing code copied. Paste it into the extension setup.');}catch(e){message('connectionStatus',e.message,true);}};
$('nickname').oninput=()=>{$('nickname').dataset.edited='true';};$('autoDemos').onchange=()=>{$('autoDemos').dataset.edited='true';};
$('saveConfig').onclick=async()=>{try{await api('/api/config','POST',{faceit_key:$('faceitKey').value,nickname:$('nickname').value,auto_demos:$('autoDemos').checked});$('faceitKey').value='';delete $('nickname').dataset.edited;delete $('autoDemos').dataset.edited;message('configStatus','Connection saved locally.');await refreshStatus();}catch(e){message('configStatus',e.message,true);}};
$('importDemo').onclick=async()=>{
  const file=$('demoFile').files[0];if(!file){message('importStatus','Choose a completed demo file.',true);return;}
  $('importDemo').disabled=true;message('importStatus','Uploading to your local helper...');
  try{const data=await api('/api/import-demo?match_id='+encodeURIComponent($('importMatch').value),'POST',file,true);message('importStatus',data.message);}
  catch(e){message('importStatus',e.message,true);}finally{$('importDemo').disabled=false;}
};
$('previewTab').onclick=preview;
$('liveTab').onclick=()=>{generation++;$('scoutButton').disabled=false;$('liveTab').classList.add('active');$('previewTab').classList.remove('active');$('liveControls').hidden=false;view.status('Paste a matchroom link. Your extension runs this step automatically.');};
$('scoutButton').onclick=()=>{teamId='';scout();};
$('matchLink').oninput=()=>{teamId='';};
(async()=>{
  const hash=new URLSearchParams(location.hash.slice(1));
  token=hash.get('pair')||'';
  if(!token){if(extensionPage)token=(await chrome.storage.local.get('localToken')).localToken||'';else token=localStorage.getItem('siteScoutToken')||'';}
  if(hash.has('pair')){history.replaceState(null,'',location.pathname);await persistToken();}
  $('pairToken').value=token;
  await Promise.all([preview(),refreshStatus()]);setInterval(refreshStatus,7000);
})();
