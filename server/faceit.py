import json
import re
import threading
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from .analysis import map_name

MATCH_PATTERN=re.compile(r'^1-[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$',re.I)

class FaceitError(Exception):
    def __init__(self,message,status=502):
        super().__init__(message)
        self.status=status

def match_id_from(value):
    value=str(value or '').strip()
    if MATCH_PATTERN.fullmatch(value):
        return value.lower()
    found=re.search(r'/cs2/room/(1-[a-f0-9-]{36})(?:[/?#]|$)',value,re.I)
    if found and MATCH_PATTERN.fullmatch(found.group(1)):
        return found.group(1).lower()
    raise ValueError('Paste a FACEIT CS2 matchroom link or match ID.')

def picked_map(match):
    voting=match.get('voting') or {}
    picks=(voting.get('map') or {}).get('pick',[]) if isinstance(voting,dict) else []
    if isinstance(picks,str):
        picks=[picks]
    choices=[map_name(p) for p in picks if isinstance(p,str)]
    choices=[p for p in choices if p]
    return choices[0] if len(choices)==1 else None

class Faceit:
    def __init__(self,store,key_getter):
        self.store=store
        self.key_getter=key_getter
        self.lock=threading.Lock()
        self.next_request=0
        self.cooldown_until=0

    def get(self,path,ttl=300):
        key=self.key_getter()
        if not key:
            raise FaceitError('Add your FACEIT server-side Data API key in the local dashboard.',428)
        cached=self.store.cache_get(path)
        if cached is not None:
            return cached
        with self.lock:
            now=time.monotonic()
            if now < self.cooldown_until:
                raise FaceitError('FACEIT request limit reached. Cached evidence remains available; retry in a minute.',429)
            delay=max(0,self.next_request-now)
            self.next_request=max(now,self.next_request)+.22
        if delay:
            time.sleep(delay)
        req=Request('https://open.faceit.com/data/v4'+path,headers={'Authorization':'Bearer '+key,'Accept':'application/json','User-Agent':'SiteScout/0.1'})
        try:
            with urlopen(req,timeout=8) as response:
                raw=response.read(4*1024*1024+1)
                if len(raw)>4*1024*1024:
                    raise FaceitError('FACEIT response was larger than expected.')
                result=json.loads(raw)
        except HTTPError as e:
            if e.code in (401,403):
                raise FaceitError('FACEIT rejected the API key. Check its type and permissions in the Developer Portal.',401)
            if e.code==429:
                with self.lock:
                    self.cooldown_until=time.monotonic()+60
                raise FaceitError('FACEIT request limit reached. Cached evidence remains available; retry in a minute.',429)
            if e.code==404:
                raise FaceitError('FACEIT could not find that match or player.',404)
            raise FaceitError('FACEIT returned HTTP '+str(e.code)+'.')
        except (URLError,TimeoutError,OSError):
            raise FaceitError('Could not reach FACEIT. Check your connection; cached evidence remains available.')
        self.store.cache_set(path,result,ttl)
        return result

    def match(self,match_id):
        return self.get('/matches/'+match_id,ttl=10)

    def stats(self,player_id):
        if not re.fullmatch(r'[a-f0-9-]{36}',player_id,re.I):
            return {'items':[]}
        return self.get('/players/'+player_id+'/games/cs2/stats?offset=0&limit=30',ttl=600)

    def history(self,player_id):
        if not re.fullmatch(r'[a-f0-9-]{36}',player_id,re.I):
            return {'items':[]}
        return self.get('/players/'+player_id+'/history?game=cs2&offset=0&limit=20',ttl=300)
