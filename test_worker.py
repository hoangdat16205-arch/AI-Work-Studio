"""Real subprocess/HTTP bridge tests using a CLI protocol fixture, not AI."""
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from flask import Flask,jsonify
from werkzeug.serving import make_server
from studio_company import register_company
from tools.company_client import BridgeClient
from tools.company_worker import run_mission,verify_cli

FAKE_CLI=r'''
import json,os,re,sys
from pathlib import Path
args=sys.argv[1:]
if args==['--version']:print('protocol-fixture-1');raise SystemExit
if '--help' in args:print('--agent --format --attach --file');raise SystemExit
if args[0]=='serve':
 from http.server import HTTPServer,BaseHTTPRequestHandler
 class Handler(BaseHTTPRequestHandler):
  def do_GET(self):
   self.send_response(200);self.end_headers();self.wfile.write(b'{"healthy":true}')
  def log_message(self,*args):pass
 HTTPServer(('127.0.0.1',int(args[args.index('--port')+1])),Handler).serve_forever()
elif args[0]=='run':
 if os.environ.get('FIXTURE_NO_REPORT')=='true':print('No final report fixture');raise SystemExit
 import requests
 brief=Path(args[args.index('--file')+1]);mission=re.search(r'Mission ID: ([a-f0-9]+)',brief.read_text()).group(1)
 root=Path.cwd();runtime=json.loads((brief.parent/'runtime.json').read_text());token=(root/'.ai-company/bridge-token').read_text().strip()
 client=requests.Session();client.trust_env=False;client.headers['Authorization']='Bearer '+token
 base=os.environ['AI_COMPANY_URL'];data=client.get(base+'/api/company/missions/'+mission,timeout=5).json()['mission']
 result=[]
 for task in data['tasks']:
  for status in ['started','submitted']:
   response=client.post(base+'/api/company/worker/'+mission+'/task',json={'lease':runtime['lease'],'task':task['id'],'status':status,'summary':'Protocol fixture report','evidence':['Fixture artifact'],'verdict':'pass'},timeout=5)
   response.raise_for_status()
  result.append({'id':task['id'],'verdict':'pass','summary':'Protocol fixture report','evidence':['Fixture artifact']})
 (brief.parent/'result.json').write_text(json.dumps({'overall':'pass','summary':'Protocol fixture; no AI execution','tasks':result}))
 print(json.dumps({'type':'fixture_complete','tasks':len(result)}))
'''


class WorkerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='company worker ');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        app=Flask('worker-fixture')
        @app.errorhandler(ValueError)
        def invalid(e):return jsonify(ok=False,error=str(e)),400
        self.store=register_company(app,self.root,SimpleNamespace(text=lambda *a:('', 'fixture')))
        self.server=make_server('127.0.0.1',0,app);threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        env=patch.dict(os.environ,{'STUDIO_DATA_ROOT':str(self.root),'ENABLE_KILO_BRIDGE':'true'});env.start();self.addCleanup(env.stop)
        self.client=BridgeClient(self.root,f'http://127.0.0.1:{self.server.server_port}');self.addCleanup(self.client.http.close)
        fixture=self.root/'kilo fixture.py';fixture.write_text(FAKE_CLI);self.command=[sys.executable,str(fixture)]
    def mission(self):
        mission=self.store.create({'title':'Fixture','brief':'Protocol test','kind':'content'},SimpleNamespace(text=lambda *a:('', 'fixture')))
        self.store.queue(mission['id']);return self.store.claim('fixture-worker','fixture-version')
    def test_real_process_and_http_lifecycle(self):
        self.assertEqual(verify_cli(self.command,self.root),'protocol-fixture-1')
        mission=self.mission();result=run_mission(self.client,mission,self.command,'fixture-worker','fixture-version',15)
        self.assertEqual(result['mission']['status'],'completed');self.assertTrue(all(t['status']=='completed' for t in result['mission']['tasks']))
        self.assertFalse((self.root/'.ai-company/missions'/mission['id']/'runtime.json').exists())
    def test_success_exit_without_report_needs_review(self):
        mission=self.mission()
        with patch.dict(os.environ,{'FIXTURE_NO_REPORT':'true'}):result=run_mission(self.client,mission,self.command,'fixture-worker','fixture-version',15)
        self.assertEqual(result['mission']['status'],'needs_review')


if __name__=='__main__':unittest.main()
