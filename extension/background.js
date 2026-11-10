'use strict';
const BASE = 'http://127.0.0.1:8765';
chrome.action.onClicked.addListener(() => chrome.runtime.openOptionsPage());
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (message?.type === 'SITE_SCOUT_SETUP') {
    chrome.runtime.openOptionsPage();
    respond({ok:true});
    return;
  }
  if (message?.type !== 'SITE_SCOUT_API') return;
  const url = sender.url ? new URL(sender.url) : null;
  const trusted = url && (url.protocol === 'chrome-extension:' ||
    (url.protocol === 'https:' && ['faceit.com','www.faceit.com'].includes(url.hostname)));
  const path = message.path;
  const method = message.method || 'GET';
  const allowed = (method === 'GET' && (/^\/api\/jobs\/[a-f0-9-]{36}$/.test(path) || ['/api/health','/api/status'].includes(path))) ||
    (method === 'POST' && path === '/api/scout');
  if (!trusted || !allowed) { respond({ok:false,error:'Request not permitted.'}); return; }
  (async () => {
    const {localToken} = await chrome.storage.local.get('localToken');
    if (!localToken) throw new Error('Open Site Scout setup and pair the extension with your local helper.');
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(BASE + path, {method,signal:controller.signal,
        headers:{'Authorization':'Bearer '+localToken,'Content-Type':'application/json'},
        ...(method === 'POST' ? {body:JSON.stringify(message.body || {})} : {})});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Local helper error.');
      respond({ok:true,data});
    } finally { clearTimeout(timer); }
  })().catch(error => respond({ok:false,error:error.name === 'AbortError' ? 'Local helper timed out. Cached evidence will remain visible.' :
    error.message === 'Failed to fetch' ? 'Start the local helper on this PC, then reconnect.' : error.message}));
  return true;
});
