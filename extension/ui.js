/* Shared renderer. Nicknames, reports and errors are always rendered as text. */
(function (root) {
  'use strict';
  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }
  function percent(value) { return Number.isFinite(value) ? Math.round(value)+'%' : 'Unavailable'; }
  function mapLabel(value) { return value ? value.replace('de_','').replace(/^./,c=>c.toUpperCase()) : 'Waiting for map'; }
  function briefText(job) {
    if (!job.brief) return 'Site Scout: briefing is loading.';
    const b=job.brief;
    return ['Site Scout | '+mapLabel(b.map), ...b.findings.map(f=>f.title+'. '+f.evidence),
      'Likely CT positions: '+b.players.map(p=>p.nickname+': '+p.position.label).join('; '),
      'Coverage: '+b.coverage+'/'+b.total_players+'. Historical tendencies; confirm their current setup.'].join('\n');
  }
  function mount(container, options={}) {
    const shell=el('section','scout-shell');
    shell.setAttribute('aria-label','Site Scout pre-match briefing');
    const header=el('header','scout-header');
    const brand=el('div','scout-brand');
    brand.append(el('span','scout-mark','S'),el('div','', 'SITE SCOUT'));
    const actions=el('div','scout-actions');
    if (options.onSetup) { const button=el('button','scout-icon','Setup'); button.onclick=options.onSetup; actions.append(button); }
    if (options.onMinimize) { const button=el('button','scout-icon','Hide'); button.onclick=options.onMinimize; actions.append(button); }
    header.append(brand,actions);
    const body=el('div','scout-body');
    shell.append(header,body); container.append(shell);
    let lastJob=null;
    function status(message) { body.replaceChildren(el('div','scout-empty',message)); }
    function error(message) {
      body.replaceChildren(el('div','scout-error',message));
      if (options.onRetry) { const retry=el('button','scout-button','Reconnect'); retry.onclick=options.onRetry; body.append(retry); }
    }
    function render(job) {
      lastJob=job;
      body.replaceChildren();
      if (job.example) body.append(el('div','scout-preview-banner','SYNTHETIC PREVIEW | Invented players and results.'));
      if (job.status==='error') { error(job.error); return; }
      if (job.status==='choose_team') {
        body.append(el('h2','scout-title','Which team are you on?'),el('p','scout-muted','Choose your team once for this match. Add your nickname in Setup to select automatically.'));
        for (const team of job.teams || []) {
          const button=el('button','scout-team-button',team.name+' | '+team.players.map(p=>p.nickname).join(', '));
          button.onclick=()=>options.onChooseTeam?.(team.id); body.append(button);
        }
        return;
      }
      if (!job.brief) { status('Identifying the lobby and checking cached evidence...'); return; }
      const b=job.brief;
      const overline=el('div','scout-overline',job.example ? 'LAYOUT PREVIEW' : 'YOUR UPCOMING MATCH');
      const heading=el('div','scout-heading');
      heading.append(el('h2','scout-title',mapLabel(b.map)),el('span','scout-badge',job.status==='partial'?'Updating':'Historical evidence'));
      body.append(overline,heading,el('p','scout-subtitle',job.opponent_name || 'Opponent briefing'));
      const metrics=el('div','scout-metrics');
      for (const [value,label] of [[b.coverage+'/'+b.total_players,'position coverage'],[b.shared_matches,'shared matches'],
          [Number.isFinite(job.first_brief_ms)?(job.first_brief_ms/1000).toFixed(1)+'s':'--','first briefing']]) {
        const metric=el('div','scout-metric');metric.append(el('strong','',value),el('span','',label));metrics.append(metric);
      }
      body.append(metrics);
      if (!b.map) body.append(el('p','scout-notice','The map has not been confirmed. Site evidence appears once FACEIT publishes the pick, or you select the map below.'));
      const findings=el('div','scout-findings');
      for (const f of b.findings || []) {
        const card=el('article','scout-finding '+(f.type.startsWith('site')?'scout-priority':''));
        card.append(el('div','scout-confidence',f.confidence+' evidence'),el('h3','',f.title),el('p','',f.text),el('small','',f.evidence));
        findings.append(card);
      }
      body.append(findings);
      const positionHead=el('div','scout-section-head');positionHead.append(el('h3','','Likely CT positions'),el('span','scout-muted','Early full-buy rounds'));
      body.append(positionHead);
      const zones=el('div','scout-zones');
      for (const zone of ['A','MID','B']) {
        const box=el('div','scout-zone');box.append(el('div','scout-zone-label',zone==='MID'?'MID / FLEX':zone+' SITE'));
        const people=b.players.filter(p=>p.position.zone===zone);
        if (!people.length) box.append(el('span','scout-muted','Unresolved'));
        for (const p of people) box.append(el('span','scout-player-chip',p.nickname));
        zones.append(box);
      }
      body.append(zones);
      for (const p of b.players) {
        const row=el('details','scout-player');
        const summary=el('summary');
        const info=el('div');info.append(el('strong','',p.nickname),el('span','scout-muted',p.position.label));
        summary.append(info,el('span','scout-round-count',p.position.rounds ? p.position.rounds+' rounds' : 'No demo data'));
        const detail=el('div','scout-player-detail');
        detail.append(el('p','',p.position.rounds ? p.position.rounds+' classified CT rounds across '+p.position.matches+' matches. '+p.position.confidence+' evidence.' : 'No eligible position observations. Scoreboard statistics do not establish a site.'));
        if (p.position.newest) detail.append(el('p','scout-muted','Newest position evidence: '+new Date(p.position.newest*1000).toLocaleDateString()));
        for (const place of p.position.positions || []) detail.append(el('span','scout-place',place.place+' | '+place.rounds+' rounds'));
        const s=p.stats?.map;
        if (s?.matches) detail.append(el('p','scout-muted','Recent map stats: '+s.matches+' matches'+(s.adr!==null&&s.adr!==undefined?' | '+s.adr+' ADR':'')+(s.kd!==null&&s.kd!==undefined?' | '+s.kd+' K/D':'')));
        row.append(summary,detail);body.append(row);
      }
      if (b.sites?.length) {
        body.append(el('h3','scout-site-title','Site contact outcomes'));
        const siteGrid=el('div','scout-sites');
        for (const site of b.sites) {
          const box=el('div','scout-site');box.append(el('strong','',site.site+' site'));
          box.append(el('small','',site.basis==='prior_lineups'?'Prior-lineup history':'Exact-lineup history'));
          if (site.attacks) {
            box.append(el('span','scout-site-rate',percent(site.hold_rate)),el('span','scout-muted','contacts without a plant'),
              el('small','',site.attacks+' attacks | '+site.matches+' '+(site.basis==='prior_lineups'?'prior':'shared')+' matches'),
              el('small','',site.confidence+' evidence | retakes: '+percent(site.retake_rate)));
          } else box.append(el('span','scout-muted','Needs shared-lineup demos'));
          siteGrid.append(box);
        }
        body.append(siteGrid);
      }
      const footer=el('div','scout-footer');
      const copy=el('button','scout-button','Copy team brief');
      copy.onclick=async()=>{ try { await navigator.clipboard.writeText(briefText(lastJob)); copy.textContent='Copied'; setTimeout(()=>copy.textContent='Copy team brief',1800); } catch { copy.textContent='Clipboard unavailable'; } };
      footer.append(copy,el('span','scout-muted','Updated '+new Date((job.updated_at || Date.now()/1000)*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})));
      body.append(footer);
      if (job.errors?.length) body.append(el('p','scout-notice',job.errors.join(' ')));
      const method=el('details','scout-method');method.append(el('summary','','How to read this'),el('p','',b.method));body.append(method);
    }
    return {render,status,error,shell};
  }
  root.SiteScout={mount,briefText,percent,mapLabel};
})(typeof window!=='undefined'?window:globalThis);
