"""An explicitly synthetic, disposable server for browser integration tests."""
import argparse
import json
import tempfile
from pathlib import Path
from server.scout import create_server
from server.jobs import Jobs
from tests.fixtures import FakeFaceit,evidence

class FixtureJobs(Jobs):
    def public(self,job):
        result=super().public(job)
        result['example']=True
        return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config-out',required=True);args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='site-scout-fixture-') as folder:
        server=create_server(8765,folder)
        app=server.app
        app.save_config({'nickname':'Sonu','auto_demos':False})
        app.api=FakeFaceit()
        app.jobs=FixtureJobs(app.store,app.api,app.config)
        for index in range(1,5):app.store.put_report(evidence(index))
        Path(args.config_out).write_text(json.dumps({'token':app.settings['local_token']}),encoding='utf-8')
        print('Synthetic browser fixture ready.',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close()

if __name__=='__main__':main()
