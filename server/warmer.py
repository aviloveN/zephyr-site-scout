"""Bounded, low-priority demo retrieval. No cookies or private FACEIT APIs."""
import gzip
import bz2
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from urllib.request import Request,urlopen,HTTPRedirectHandler,build_opener
from .analysis import map_name
from .demo_import import validate_report

MAX_DEMO=512*1024*1024

def approved_url(url):
    parsed=urlparse(url)
    host=(parsed.hostname or '').lower()
    return parsed.scheme=='https' and not parsed.username and not parsed.password and parsed.port in (None,443) and any(host==d or host.endswith('.'+d) for d in ('faceit.com','faceit.net','faceit-cdn.net','cloudfront.net'))

class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not approved_url(newurl):
            raise ValueError('Demo redirect is outside approved FACEIT delivery hosts.')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

class Warmer:
    def __init__(self,store,api,config,root,data_dir):
        self.store,self.api,self.config,self.root,self.data_dir=store,api,config,root,data_dir
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='demo-cache')
        self.lock=threading.Lock()
        self.pending=set()
        self.events=[]

    def event(self,message):
        with self.lock:
            self.events=([{'at':time.time(),'message':message}]+self.events)[:20]

    def available(self):
        return importlib.util.find_spec('demoparser2') is not None

    def schedule(self,players,selected_map,current_match):
        if not self.config().get('auto_demos',True) or not self.available():
            return
        for p in players:
            player_id=p.get('player_id','')
            key=(player_id,selected_map)
            with self.lock:
                if key in self.pending or len(self.pending)>=10:
                    continue
                if self.store.cache_get('warmed:'+player_id+':'+selected_map):
                    continue
                self.pending.add(key)
            self.pool.submit(self.warm_player,p,selected_map,current_match,key)

    def warm_player(self,player,selected_map,current_match,key):
        try:
            history=self.api.history(player['player_id']).get('items',[])
            inspected=0
            imported=0
            for old in history:
                match_id=old.get('match_id','')
                if match_id==current_match or self.store.has_report(match_id):
                    continue
                if old.get('status')!='FINISHED':
                    continue
                if not old.get('finished_at') or old['finished_at']<time.time()-30*86400:
                    continue
                if inspected>=6 or imported>=1:
                    break
                inspected+=1
                details=self.api.match(match_id)
                if details.get('status')!='FINISHED':
                    continue
                from .faceit import picked_map
                old_map=picked_map(details)
                if not old_map:
                    stats=self.api.get('/matches/'+match_id+'/stats',ttl=86400)
                    maps={map_name(r.get('round_stats',{}).get('Map')) for r in stats.get('rounds',[])}-{None}
                    old_map=next(iter(maps)) if len(maps)==1 else None
                if old_map!=selected_map:
                    continue
                urls=[u for u in details.get('demo_url',[]) if isinstance(u,str) and approved_url(u)]
                if not urls:
                    self.event('No accessible official demo URL for '+player.get('nickname','player')+'. You can import the completed demo manually.')
                    continue
                self.download_and_import(urls[0],match_id,details['finished_at'])
                imported+=1
            self.store.cache_set('warmed:'+player['player_id']+':'+selected_map,True,600)
        except Exception as e:
            self.event('Demo evidence unavailable for '+player.get('nickname','player')+': '+str(e)[:180])
        finally:
            with self.lock:
                self.pending.discard(key)

    def download_and_import(self,url,match_id,played_at):
        if not approved_url(url):
            raise ValueError('Unapproved demo URL.')
        with tempfile.TemporaryDirectory(prefix='site-scout-',dir=str(self.data_dir)) as folder:
            path=Path(folder)/'download'
            opener=build_opener(SafeRedirect())
            with opener.open(Request(url,headers={'User-Agent':'SiteScout/0.1'}),timeout=15) as response, path.open('wb') as target:
                total=0
                deadline=time.monotonic()+30
                while True:
                    if time.monotonic()>deadline:
                        raise TimeoutError('Demo download exceeded its 30-second budget.')
                    chunk=response.read(1024*1024)
                    if not chunk:
                        break
                    total+=len(chunk)
                    if total>MAX_DEMO:
                        raise ValueError('Demo exceeds the 512 MB download limit.')
                    target.write(chunk)
            self.import_file(path,match_id,played_at)

    def import_file(self,path,match_id,played_at):
        if not self.available():
            raise ValueError('Install demo support first using the included installer.')
        with tempfile.TemporaryDirectory(prefix='site-scout-parse-',dir=str(self.data_dir)) as folder:
            folder=Path(folder)
            with Path(path).open('rb') as source:
                magic=source.read(4)
            demo=Path(path)
            decompressor=gzip.open if magic[:2]==b'\x1f\x8b' else (bz2.open if magic[:3]==b'BZh' else None)
            if decompressor:
                demo=folder/'match.dem'
                total=0
                with decompressor(path,'rb') as source,demo.open('wb') as target:
                    while True:
                        chunk=source.read(1024*1024)
                        if not chunk:
                            break
                        total+=len(chunk)
                        if total>MAX_DEMO:
                            raise ValueError('Expanded demo exceeds the 512 MB limit.')
                        target.write(chunk)
            if magic==b'\x28\xb5\x2f\xfd':
                try:
                    import zstandard
                except ImportError:
                    raise ValueError('Zstandard support is missing. Run the demo-support installer again.')
                demo=folder/'match.dem'
                total=0
                with Path(path).open('rb') as source,demo.open('wb') as target,zstandard.ZstdDecompressor().stream_reader(source) as reader:
                    while True:
                        chunk=reader.read(1024*1024)
                        if not chunk:
                            break
                        total+=len(chunk)
                        if total>MAX_DEMO:
                            raise ValueError('Expanded demo exceeds the 512 MB limit.')
                        target.write(chunk)
            with demo.open('rb') as source:
                valid_magic=source.read(8)==b'PBDEMS2\x00'
            if not valid_magic:
                raise ValueError('Expected a CS2 .dem file, optionally gzip, bzip2 or zstd compressed.')
            output=folder/'report.json'
            command=[sys.executable,'-m','server.demo_import',str(demo),'--match-id',match_id,'--played-at',str(played_at),'--output',str(output)]
            options={'cwd':str(self.root),'capture_output':True,'text':True,'timeout':45}
            if sys.platform=='win32':
                options['creationflags']=subprocess.BELOW_NORMAL_PRIORITY_CLASS
            result=subprocess.run(command,**options)
            if result.returncode:
                raise ValueError('Demo parsing failed. Parser format support may need updating. '+result.stderr.strip().split('\n')[-1][:150])
            report=validate_report(json.loads(output.read_text(encoding='utf-8')))
            self.store.put_report(report)
            self.event('Added '+str(len(report['rounds']))+' completed rounds on '+report['map']+'.')
            return report
