import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ai_providers import AIService,ProviderError


class SelfHostedTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.calls=[]
        class HTTP:
            def json(inner,method,url,**kwargs):self.calls.append((method,url,kwargs));return self.response
        self.service=AIService(Path(self.temp.name),HTTP())
        env=patch.dict('os.environ',{'SELF_HOSTED_BASE_URL':'http://127.0.0.1:8000/v1','SELF_HOSTED_MODEL':'company/my-model','SELF_HOSTED_API_KEY':'test-secret','SELF_HOSTED_MAX_TOKENS':'8000'})
        env.start();self.addCleanup(env.stop)
    def test_compatible_text_and_private_model_names(self):
        self.response={'choices':[{'message':{'content':'Private result'}}]}
        result,model=self.service.text('self_hosted','A request','System instructions')
        self.assertEqual(result,'Private result');self.assertEqual(model,'company/my-model')
        method,url,options=self.calls[0];self.assertEqual(url,'http://127.0.0.1:8000/v1/chat/completions')
        self.assertEqual(options['json']['messages'][1]['content'],'A request');self.assertFalse(options['json']['stream'])
        self.assertEqual(options['headers']['Authorization'],'Bearer test-secret')
        status=next(p for p in self.service.status() if p['id']=='self_hosted');self.assertEqual(status['capabilities'],['text','scenes']);self.assertNotIn('test-secret',str(status))
    def test_real_catalog_contract_and_missing_model(self):
        self.response={'data':[{'id':'company/my-model'}]};self.assertIn('message',self.service.check('self_hosted'))
        self.response={'data':[{'id':'different'}]}
        with self.assertRaises(ProviderError):self.service.check('self_hosted')
    def test_malformed_responses_empty_and_bad_urls(self):
        for self.response in [{},{'choices':[{'message':{'content':''}}]},{'choices':[{'message':{'content':'x'*50001}}]}]:
            with self.assertRaises(ProviderError):self.service.text('self_hosted','Prompt','System')
        with patch.dict('os.environ',{'SELF_HOSTED_BASE_URL':'https://user:secret@host/v1'}):
            with self.assertRaises(ValueError):self.service.text('self_hosted','Prompt','System')
    def test_scene_workflow_uses_same_adapter(self):
        self.response={'choices':[{'message':{'content':'{"scenes":[{"title":"One","narration":"Hello world","prompt":"A cinematic scene"}]}'}}]}
        scenes,model=self.service.scenes('self_hosted','Hello world',1);self.assertEqual(scenes[0]['narration'],'Hello world')
    def test_output_budget_can_follow_the_private_model(self):
        self.response={'choices':[{'message':{'content':'Result'}}]}
        with patch.dict('os.environ',{'SELF_HOSTED_MAX_TOKENS':'2048'}):
            self.service.text('self_hosted','Prompt','System');self.assertEqual(self.calls[-1][2]['json']['max_tokens'],2048)
        count=len(self.calls)
        for invalid in ['0','-1','32769','not-an-integer']:
            with patch.dict('os.environ',{'SELF_HOSTED_MAX_TOKENS':invalid}):
                with self.assertRaises(ValueError):self.service.text('self_hosted','Prompt','System')
        self.assertEqual(len(self.calls),count)


if __name__=='__main__':unittest.main()
