"""Dependency-free localhost API and setup dashboard. Python 3.9+."""
import argparse
import hmac
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
import webbrowser
from .analysis import map_name
from .demo_import import validate_report
from .example import example_job
from .faceit import Faceit,FaceitError,match_id_from
from .jobs import Jobs
from .storage import Store
from .warmer import Warmer,MAX_DEMO

VERSION='0.1.0'
ROOT=Path(__file__).resolve().parent.parent

class App:
    def __init__(self,data_dir):
        self.data_dir=Path(data_dir)
        self.data_dir.mkdir(parents=True,exist_ok=True)
        self.config_path=self.data_dir/'config.json'
        self.config_lock=threading.RLock()
        if self.config_path.exists():
            self.settings=json.loads(self.config_path.read_text(encoding='utf-8'))
        else:
            self.settings={'local_token':secrets.token_urlsafe(32),'faceit_key':'','nickname':'','auto_demos':True}
            self.save_config({})
        self.store=Store(self.data_dir/'evidence.sqlite3')
        self.api=Faceit(self.store,lambda:self.settings.get('faceit_key') or os.environ.get('FACEIT_API_KEY',''))
        self.warmer=Warmer(self.store,self.api,self.config,ROOT,self.data_dir)
        self.jobs=Jobs(self.store,self.api,self.config,self.warmer)

    def config(self):
        with self.config_lock:
            return dict(self.settings)

    def save_config(self,values):
        with self.config_lock:
            self.settings.update(values)
            temp=self.config_path.with_suffix('.tmp')
            temp.write_text(json.dumps(self.settings),encoding='utf-8')
            os.chmod(temp,0o600)
            temp.replace(self.config_path)

class Handler(BaseHTTPRequestHandler):
    server_version='SiteScout/'+VERSION

    @property
    def app(self):
        return self.server.app

    def log_message(self,fmt,*args):
        # Never log Authorization headers, pairing fragments, request bodies or keys.
        pass

    def allowed_origin(self):
        origin=self.headers.get('Origin','')
        if not origin:
            return True
        p=urlparse(origin)
        return (p.scheme=='chrome-extension' and bool(p.netloc)) or (p.scheme=='http' and p.hostname in ('127.0.0.1','localhost') and p.port==self.server.server_port)

    def allowed_host(self):
        return self.headers.get('Host') in ('127.0.0.1:'+str(self.server.server_port),'localhost:'+str(self.server.server_port))

    def auth(self):
        expected='Bearer '+self.app.settings['local_token']
        return self.allowed_origin() and hmac.compare_digest(self.headers.get('Authorization','').encode('utf-8'),expected.encode('utf-8'))

    def headers_for(self,status,content_type='application/json; charset=utf-8',length=None):
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        if length is not None:
            self.send_header('Content-Length',str(length))
        if self.allowed_origin() and self.headers.get('Origin'):
            self.send_header('Access-Control-Allow-Origin',self.headers['Origin'])
            self.send_header('Vary','Origin')
        self.end_headers()

    def send_json(self,status,value):
        raw=json.dumps(value,allow_nan=False).encode('utf-8')
        self.headers_for(status,length=len(raw))
        self.wfile.write(raw)

    def json_body(self):
        length=int(self.headers.get('Content-Length','0'))
        if length<=0 or length>2*1024*1024:
            raise ValueError('Request body must be between 1 byte and 2 MB.')
        value=json.loads(self.rfile.read(length))
        if not isinstance(value,dict):
            raise ValueError('Expected a JSON object.')
        return value

    def do_OPTIONS(self):
        if not self.allowed_origin() or not self.allowed_host():
            return self.send_json(403,{'error':'Origin not allowed.'})
        self.send_response(204)
        if self.headers.get('Origin'):
            self.send_header('Access-Control-Allow-Origin',self.headers['Origin'])
        self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type')
        self.send_header('Access-Control-Allow-Private-Network','true')
        self.end_headers()

    def do_GET(self):
        if not self.allowed_host():
            return self.send_json(403,{'error':'Invalid host.'})
        path=urlparse(self.path).path
        static={'/':'dashboard.html','/preview':'dashboard.html','/dashboard.js':'dashboard.js','/ui.js':'ui.js','/styles.css':'styles.css'}
        if path in static:
            file=ROOT/'extension'/static[path]
            raw=file.read_bytes()
            mime='text/html' if file.suffix=='.html' else ('text/javascript' if file.suffix=='.js' else 'text/css')
            self.headers_for(200,mime+'; charset=utf-8',len(raw))
            self.wfile.write(raw)
            return
        if path=='/api/health':
            return self.send_json(200,{'app':'site-scout','version':VERSION})
        if path=='/api/example':
            return self.send_json(200,example_job())
        if not self.auth():
            return self.send_json(401,{'error':'Pair this browser with the local helper first.'})
        if path=='/api/status':
            return self.send_json(200,{'version':VERSION,'configured':bool(self.app.api.key_getter()),'nickname':self.app.settings.get('nickname',''),
                'auto_demos':self.app.settings.get('auto_demos',True),'parser_available':self.app.warmer.available(),
                'cache':self.app.store.counts(),'pending_demos':len(self.app.warmer.pending),'events':self.app.warmer.events})
        if path.startswith('/api/jobs/'):
            job=self.app.jobs.get(path.split('/')[-1])
            return self.send_json(200,job) if job else self.send_json(404,{'error':'Briefing expired. Start scouting again.'})
        self.send_json(404,{'error':'Not found.'})

    def do_POST(self):
        if not self.allowed_host() or not self.auth():
            return self.send_json(401,{'error':'Pair this browser with the local helper first.'})
        path=urlparse(self.path).path
        try:
            if path=='/api/import-demo':
                params=parse_qs(urlparse(self.path).query)
                match_id=match_id_from(params.get('match_id',[''])[0])
                details=self.app.api.match(match_id)
                if details.get('status')!='FINISHED':
                    raise ValueError('Import only completed-match demos. This match has not finished.')
                if not self.app.warmer.available():
                    raise ValueError('Install demo support first using the included installer.')
                length=int(self.headers.get('Content-Length','0'))
                if not 8<=length<=MAX_DEMO:
                    raise ValueError('Choose a completed CS2 demo smaller than 512 MB.')
                file=tempfile.NamedTemporaryFile(delete=False,dir=str(self.app.data_dir),suffix='.dem')
                target=Path(file.name)
                try:
                    left=length
                    self.connection.settimeout(30)
                    while left:
                        chunk=self.rfile.read(min(left,1024*1024))
                        if not chunk:
                            raise ValueError('Demo upload was interrupted.')
                        file.write(chunk)
                        left-=len(chunk)
                    file.close()
                    def run_import():
                        try:
                            self.app.warmer.import_file(target,match_id,details['finished_at'])
                        except Exception as e:
                            self.app.warmer.event(str(e)[:220])
                        finally:
                            target.unlink(missing_ok=True)
                    self.app.warmer.pool.submit(run_import)
                    return self.send_json(202,{'queued':True,'message':'Demo queued for analysis. The dashboard will show the result.'})
                except Exception:
                    file.close()
                    target.unlink(missing_ok=True)
                    raise
            data=self.json_body()
            if path=='/api/config':
                values={}
                if 'faceit_key' in data:
                    key=str(data['faceit_key']).strip()
                    if key and (len(key)>250 or not all(c.isascii() and (c.isalnum() or c in '-_.') for c in key)):
                        raise ValueError('The API key contains unexpected characters.')
                    # Empty password field keeps the existing key. Explicit remove is separate.
                    if key:
                        values['faceit_key']=key
                if data.get('remove_key'):
                    values['faceit_key']=''
                if 'nickname' in data:
                    values['nickname']=str(data['nickname']).strip()[:50]
                if 'auto_demos' in data:
                    values['auto_demos']=bool(data['auto_demos'])
                self.app.save_config(values)
                return self.send_json(200,{'saved':True})
            if path=='/api/scout':
                match_id=match_id_from(data.get('match_id'))
                selected=map_name(data.get('map'))
                return self.send_json(202,self.app.jobs.start(match_id,str(data.get('team_id',''))[:100],selected))
            if path=='/api/import-evidence':
                report=validate_report(data)
                self.app.store.put_report(report)
                return self.send_json(200,{'imported':True,'rounds':len(report['rounds'])})
            self.send_json(404,{'error':'Not found.'})
        except FaceitError as e:
            self.send_json(e.status,{'error':str(e)})
        except (ValueError,KeyError,TypeError,json.JSONDecodeError) as e:
            self.send_json(400,{'error':str(e)[:250]})
        except Exception:
            self.send_json(500,{'error':'The local helper encountered an error. No unsupported scouting claims were added.'})

def create_server(port=8765,data_dir=None):
    app=App(data_dir or ROOT/'data')
    httpd=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    httpd.daemon_threads=True
    httpd.app=app
    return httpd

def main():
    parser=argparse.ArgumentParser(description='Site Scout local helper')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--data-dir')
    parser.add_argument('--open',action='store_true')
    args=parser.parse_args()
    try:
        httpd=create_server(args.port,args.data_dir)
    except OSError as e:
        print('Could not start the helper on port '+str(args.port)+': '+str(e),file=sys.stderr)
        raise SystemExit(1)
    url='http://127.0.0.1:'+str(httpd.server_port)+'/#pair='+httpd.app.settings['local_token']
    print('Site Scout '+VERSION+' is running locally. Keep this window open.\nSetup: '+url,flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

if __name__=='__main__':
    main()
