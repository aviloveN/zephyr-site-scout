(() => {
  'use strict';
  const matchPattern=/\/cs2\/room\/(1-[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})(?:\/|$)/i;
  let host,root,view,matchId='',teamId='',selectedMap='',generation=0,cycleTimer,requestBusy=false,startedAt=0;
  const send=message=>new Promise((resolve,reject)=>chrome.runtime.sendMessage(message,result=>{
    if (chrome.runtime.lastError) return reject(new Error('Extension was reloaded. Refresh this FACEIT tab.'));
    if (!result?.ok) return reject(new Error(result?.error || 'Local helper unavailable.'));
    resolve(result.data);
  }));
  const api=(path,method='GET',body)=>send({type:'SITE_SCOUT_API',path,method,body});
  function mount() {
    if (host) return;
    host=document.createElement('div');host.id='site-scout-extension-root';
    Object.assign(host.style,{position:'fixed',top:'86px',right:'18px',width:'440px',maxWidth:'calc(100vw - 24px)',zIndex:'2147483000'});
    root=host.attachShadow({mode:'open'});
    const css=document.createElement('link');css.rel='stylesheet';css.href=chrome.runtime.getURL('styles.css');root.append(css);
    view=SiteScout.mount(root,{onSetup:()=>chrome.runtime.sendMessage({type:'SITE_SCOUT_SETUP'}),onRetry:()=>start(),
      onChooseTeam:id=>{teamId=id;start();},onMinimize:()=>{
        view.shell.hidden=true;
        const pill=document.createElement('button');pill.className='scout-button scout-reopen';pill.textContent='Open Site Scout';
        pill.onclick=()=>{pill.remove();view.shell.hidden=false;};root.append(pill);
      }});
    const controls=document.createElement('div');controls.className='scout-inline-controls';
    const map=document.createElement('select');map.setAttribute('aria-label','Confirmed map override');
    for (const name of ['', 'mirage','dust2','inferno','ancient','anubis','nuke','train','overpass','vertigo','cache']) {
      const option=document.createElement('option');option.value=name?'de_'+name:'';option.textContent=name?SiteScout.mapLabel(name):'Map: detect automatically';map.append(option);
    }
    map.onchange=()=>{selectedMap=map.value;start();};
    controls.append(map);root.append(controls);document.documentElement.append(host);
  }
  function clear() {
    generation++;clearTimeout(cycleTimer);host?.remove();host=null;view=null;root=null;requestBusy=false;
  }
  async function start() {
    clearTimeout(cycleTimer);const current=++generation;requestBusy=true;startedAt=Date.now();
    view?.status('Checking this lobby and retrieving cached evidence...');
    try {
      let job=await api('/api/scout','POST',{match_id:matchId,team_id:teamId,map:selectedMap||null});
      while (current===generation) {
        view.render(job);
        if (job.team_id) teamId=job.team_id;
        if (['choose_team','error'].includes(job.status)) break;
        if (Date.now()-startedAt>90000) break;
        await new Promise(resolve=>setTimeout(resolve,job.brief?2500:700));
        if (current!==generation) break;
        if (job.status==='awaiting_map' && !selectedMap && Date.now()*0.001-job.created_at>12) {
          job=await api('/api/scout','POST',{match_id:matchId,team_id:teamId});
        } else job=await api('/api/jobs/'+job.id);
      }
    } catch (error) { if (current===generation) view?.error(error.message); }
    finally { if (current===generation) requestBusy=false; }
  }
  function detect() {
    const id=location.pathname.match(matchPattern)?.[1] || '';
    if (id!==matchId) {
      clear();matchId=id;teamId='';selectedMap='';
      if (id) { mount();start(); }
    }
  }
  // URL polling survives FACEIT SPA navigation without touching React internals.
  setInterval(detect,1000);detect();
})();
