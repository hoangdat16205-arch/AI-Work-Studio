import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from flask import Flask,jsonify
from company_roster import ROSTER
from studio_company import CompanyStore,register_company,validate_plan,default_plan
from tools.company_worker import resolve_kilo,safe_result


class CompanyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.store=CompanyStore(self.root)
        self.service=SimpleNamespace(text=lambda *a:('','mock'))
    def mission(self,kind='software'):return self.store.create({'title':'Build project','brief':'A real user goal','kind':kind},self.service)
    def claim(self,mission):self.store.queue(mission['id']);return self.store.claim('worker','test-cli')
    def test_agent_configuration_real_roster_and_permissions(self):
        files=list(Path(__file__).with_name('.kilo').joinpath('agents').glob('*.md'));self.assertEqual(len(files),24)
        definitions={p.stem:json.loads(p.read_text().split('---')[1]) for p in files}
        self.assertEqual(set(definitions),{r['id'] for r in ROSTER});manager=definitions['ai-manager'];self.assertEqual(manager['mode'],'primary')
        self.assertEqual(set(manager['permission']['task'])-{'*'},set(definitions)-{'ai-manager'})
        for id,definition in definitions.items():
            self.assertEqual(definition['permission']['read']['.accounts/*'],'deny')
            self.assertEqual(definition['permission']['edit']['tools/*'],'deny')
            if id!='ai-manager':self.assertEqual(definition['permission']['task']['*'],'deny')
    def test_plan_validation_and_ai_structured_output(self):
        for kind in ['software','audit','content']:self.assertTrue(validate_plan(default_plan(kind),kind))
        broken=default_plan('software');broken[0]['depends']=['t09']
        with self.assertRaises(ValueError):validate_plan(broken,'software')
        with self.assertRaises(ValueError):validate_plan([{'id':'t01','agent':'unknown','title':'x','description':'x'}],'software')
        output=json.dumps({'tasks':default_plan('audit')})
        service=SimpleNamespace(text=lambda *a:(output,'mock-model'))
        mission=self.store.create({'title':'Audit','brief':'Inspect','kind':'audit','planner':'ai','provider':'openai'},service)
        self.assertEqual(mission['source'],'ai:mock-model');self.assertEqual(mission['status'],'draft')
    def test_claim_single_checkout_and_lease_persistence(self):
        first=self.mission();second=self.mission();run=self.claim(first);self.store.queue(second['id'])
        self.assertIsNone(self.store.claim('other','test-cli'))
        reopened=CompanyStore(self.root);self.assertEqual(reopened.get(first['id'])['status'],'running')
        with self.assertRaises(ValueError):self.store.queue(first['id'])
        with self.assertRaises(ValueError):self.store.report(first['id'],'wrong',{'task':'t01','status':'started'})
        self.store.cancel(first['id']);self.assertEqual(self.store.claim('worker','test-cli')['id'],second['id'])
        with self.assertRaises(ValueError):self.store.heartbeat(run['id'],run['lease'],'worker','test')
    def test_interrupted_worker_not_retried_automatically(self):
        run=self.claim(self.mission())
        with self.store.connect() as db:db.execute('UPDATE missions SET heartbeat=0 WHERE id=?',(run['id'],))
        self.assertEqual(self.store.get(run['id'])['status'],'interrupted');self.assertIsNone(self.store.claim('worker','test'))
        self.store.queue(run['id']);self.assertIsNotNone(self.store.claim('worker','test'))
    def test_dependency_reports_and_finish_with_evidence(self):
        run=self.claim(self.mission());id=run['id'];lease=run['lease']
        with self.assertRaises(ValueError):self.store.report(id,lease,{'task':'t02','status':'started'})
        result=[]
        for task in run['tasks']:
            self.store.report(id,lease,{'task':task['id'],'status':'started'})
            self.store.report(id,lease,{'task':task['id'],'status':'submitted','summary':'Actual report','evidence':['A verified artifact'],'verdict':'pass'})
            result.append({'id':task['id'],'summary':'Actual report','evidence':['A verified artifact'],'verdict':'pass'})
        added=self.store.add_task(id,lease,{'agent':'privacy-reviewer','title':'Privacy','description':'Review','depends':['t09']})
        self.store.report(id,lease,{'task':added['id'],'status':'submitted','summary':'Privacy report'})
        result.append({'id':added['id'],'summary':'Privacy report','evidence':['Inspected data flow'],'verdict':'pass'})
        final=self.store.finish(id,lease,{'overall':'pass','summary':'All evidence attached','tasks':result},0)
        self.assertEqual(final['status'],'completed');self.assertNotIn('lease',final)
    def test_exit_zero_missing_reports_never_marked_complete(self):
        run=self.claim(self.mission());result=self.store.finish(run['id'],run['lease'],{'overall':'pass','summary':'No proof','tasks':[]},0)
        self.assertEqual(result['status'],'needs_review')
    def test_redaction_auth_csrf_and_local_boundary(self):
        app=Flask('company-test')
        @app.errorhandler(ValueError)
        def invalid(e):return jsonify(ok=False,error=str(e)),400
        store=register_company(app,self.root,self.service);client=app.test_client()
        self.assertEqual(client.get('/api/company/bootstrap',environ_overrides={'REMOTE_ADDR':'192.0.2.1'}).status_code,403)
        self.assertEqual(client.post('/api/company/missions',json={}).status_code,403)
        csrf=client.get('/api/company/bootstrap').get_json()['csrf']
        response=client.post('/api/company/missions',json={'title':'Goal','brief':'Brief'},headers={'X-Company-CSRF':csrf,'Origin':'https://other.invalid'})
        self.assertEqual(response.status_code,403)
        self.assertEqual(client.post('/api/company/worker/claim',json={'worker':'x','version':'x'}).status_code,403)
        mission=store.create({'title':'Goal','brief':'Brief'},self.service);store.queue(mission['id'])
        run=client.post('/api/company/worker/claim',json={'worker':'x','version':'x'},headers={'Authorization':'Bearer '+store.token}).get_json()['mission']
        store.log(run['id'],run['lease'],'Bearer hidden-secret and sk-abcdefghijklmnopqrst')
        self.assertNotIn('hidden-secret',store.get(run['id'])['events'][-1]['message'])
    def test_missing_cli_and_missing_final_report(self):
        with patch('shutil.which',return_value=None):
            with self.assertRaises(ValueError):resolve_kilo()
        self.assertEqual(safe_result(self.root/'missing.json')['overall'],'needs_review')


if __name__=='__main__':unittest.main()
