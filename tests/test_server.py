import json
import tempfile
import threading
import time
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from server.scout import create_server
from tests.fixtures import MATCH,FakeFaceit,evidence

class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.server=create_server(0,cls.tmp.name)
        cls.base='http://127.0.0.1:'+str(cls.server.server_port)
        cls.token=cls.server.app.settings['local_token']
        cls.server.app.api=FakeFaceit()
        cls.server.app.jobs.api=cls.server.app.api
        cls.server.app.jobs.warmer=None
        cls.server.app.save_config({'nickname':'Sonu','faceit_key':'secret-test-key'})
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close()
        cls.server.app.jobs.pool.shutdown(wait=True);cls.server.app.jobs.io.shutdown(wait=True)
        cls.server.app.store.db.close();cls.tmp.cleanup()
    def request(self,path,data=None,token=True,origin=None):
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+self.token
        if origin:headers['Origin']=origin
        req=Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        try:
            with urlopen(req,timeout=5) as response:return response.status,response.read(),response.headers
        except HTTPError as e:return e.code,e.read(),e.headers
    def test_health_is_minimal(self):
        status,raw,_=self.request('/api/health',token=False)
        self.assertEqual(status,200);self.assertNotIn(b'key',raw)
    def test_missing_pairing_rejected(self):
        self.assertEqual(self.request('/api/status',token=False)[0],401)
    def test_foreign_origin_rejected_even_with_token(self):
        self.assertEqual(self.request('/api/config',{'nickname':'Other'},origin='https://evil.example')[0],401)
    def test_extension_origin_supported(self):
        status,_,headers=self.request('/api/health',origin='chrome-extension://test')
        self.assertEqual(status,200);self.assertEqual(headers['Access-Control-Allow-Origin'],'chrome-extension://test')
    def test_dashboard_does_not_expose_token(self):
        _,raw,_=self.request('/',token=False)
        self.assertNotIn(self.token.encode(),raw)
    def test_preview_marked_and_not_persisted(self):
        status,raw,_=self.request('/api/example',token=False)
        self.assertEqual(status,200);self.assertTrue(json.loads(raw)['example'])
        self.assertEqual(self.server.app.store.counts()['demos'],0)
    def test_config_never_echoes_secret(self):
        _,raw,_=self.request('/api/config',{'faceit_key':'updated-test-secret','nickname':'Sonu'})
        self.assertNotIn(b'updated-test-secret',raw)
    def test_invalid_match_link_rejected(self):
        self.assertEqual(self.request('/api/scout',{'match_id':'anything'})[0],400)
    def test_live_job_protocol(self):
        status,raw,_=self.request('/api/scout',{'match_id':MATCH})
        self.assertEqual(status,202);job=json.loads(raw)
        for _ in range(30):
            _,raw,_=self.request('/api/jobs/'+job['id']);job=json.loads(raw)
            if job['status']=='ready':break
            time.sleep(.02)
        self.assertEqual(job['status'],'ready');self.assertEqual(len(job['brief']['players']),5)
        self.assertEqual(job['brief']['coverage'],0)
        self.assertEqual(job['brief']['findings'][0]['title'],'Site advantage is not established')
    def test_bad_evidence_rejected(self):
        self.assertEqual(self.request('/api/import-evidence',{'schema_version':999})[0],400)

if __name__=='__main__':unittest.main()
