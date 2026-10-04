import base64
import io
import json
import os
import tempfile
import time
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from flask import Flask,jsonify
import requests
from ai_providers import AIService,OfficialHTTP,ProviderError,GOOGLE_API
from github_projects import GitHubProjects
from studio_ai import register_ai
from veo_jobs import VeoJobs

class FakeHTTP:
    def __init__(self, responses):self.responses=list(responses);self.calls=[]
    def json(self,method,url,**kwargs):
        self.calls.append((method,url,kwargs))
        result=self.responses.pop(0)
        if isinstance(result,Exception):raise result
        return result
    def request(self,method,url,**kwargs):
        self.calls.append((method,url,kwargs));return self.responses.pop(0)
    def video_download(self,uri,key,destination):
        self.calls.append(('DOWNLOAD',uri,{}));destination.write_bytes(b'test-video')

class AITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{'OPENAI_API_KEY':'test-openai-secret','GEMINI_API_KEY':'test-google-secret','ANTHROPIC_API_KEY':'test-claude-secret','GEMINI_API_MODE':'interactions','GITHUB_TOKEN':'test-github-secret','GITHUB_REPO':'owner/repo','GITHUB_BRANCH':'main'},clear=True);self.env.start()
    def tearDown(self):self.env.stop();self.tmp.cleanup()

    def test_provider_formats_and_no_keys_in_status(self):
        responses=[{'output':[{'type':'message','content':[{'type':'output_text','text':'OpenAI result'}]}]},
                   {'steps':[{'type':'model_output','content':[{'type':'text','text':'Gemini result'}]}]},
                   {'content':[{'type':'text','text':'Claude result'}]}]
        http=FakeHTTP(responses);service=AIService(self.base,http)
        for provider,expected in [('openai','OpenAI result'),('gemini','Gemini result'),('claude','Claude result')]:
            self.assertEqual(service.text(provider,'hello','system')[0],expected)
        self.assertEqual(http.calls[0][1],'https://api.openai.com/v1/responses')
        self.assertEqual(http.calls[1][1],GOOGLE_API+'/interactions')
        self.assertEqual(http.calls[2][2]['headers']['anthropic-version'],'2023-06-01')
        self.assertNotIn('test-openai-secret',json.dumps(service.status()))

    def test_missing_key_and_scene_preservation(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':''}):
            with self.assertRaises(ProviderError):AIService(self.base,FakeHTTP([])).text('openai','a','b')
        valid={'scenes':[{'narration':'Xin chào.','prompt':'A sunrise','title':'Chào'}]}
        bad={'scenes':[{'narration':'Đã thay lời.','prompt':'A sunrise'}]}
        outputs=[{'content':[{'type':'text','text':json.dumps(v)}]} for v in [valid,bad]]
        service=AIService(self.base,FakeHTTP(outputs))
        self.assertEqual(service.scenes('claude','Xin chào.',1)[0][0]['duration'],8)
        with self.assertRaises(ProviderError):service.scenes('claude','Xin chào.',1)

    def test_image_persisted(self):
        encoded=base64.b64encode(b'png-file').decode()
        http=FakeHTTP([{'steps':[{'type':'model_output','content':[{'type':'image','mime_type':'image/png','data':encoded}]}]}])
        files,_=AIService(self.base,http).image('gemini','sunrise','16:9')
        self.assertEqual((self.base/'studio_assets'/files[0]['id']).read_bytes(),b'png-file')
        self.assertEqual(http.calls[0][2]['json']['response_format']['aspect_ratio'],'16:9')

    def test_http_errors_do_not_echo_keys(self):
        http=OfficialHTTP()
        response=SimpleNamespace(ok=False,status_code=401,text='secret error body')
        with patch.object(http.session,'request',return_value=response):
            with self.assertRaises(ProviderError) as ctx:http.json('GET','https://api.openai.com/v1/models')
        self.assertNotIn('secret',str(ctx.exception))
        with patch.object(http.session,'request',side_effect=requests.ConnectionError('api-key-secret')):
            with self.assertRaises(ProviderError) as ctx:http.json('GET',GOOGLE_API+'/models')
        self.assertNotIn('api-key-secret',str(ctx.exception))
        with self.assertRaises(ProviderError):http.video_download('http://127.0.0.1/private','secret',self.base/'bad.mp4')

    def test_veo_batch_operation_persistence_resume(self):
        http=FakeHTTP([{'name':'models/veo-3.1-generate-preview/operations/op1'},
                       {'done':False},{'done':True,'response':{'generateVideoResponse':{'generatedSamples':[{'video':{'uri':GOOGLE_API+'/files/video1'}}]}}}])
        service=AIService(self.base,http);jobs=VeoJobs(service,poll_interval=0)
        jobs.pool.shutdown(wait=True)
        jobs.pool=SimpleNamespace(submit=lambda fn,id:fn(id))
        id=jobs.start([{'index':3,'prompt':'A sunrise','title':'Scene 3'}],'9:16','720p')
        self.assertEqual(jobs.get(id)['state'],'done')
        self.assertEqual(jobs.get(id)['files'][0]['scene_index'],3)
        saved=json.loads((self.base/'veo_jobs'/f'{id}.json').read_text())
        saved['state']='running';saved['scenes'][0]['state']='waiting';saved['scenes'][0]['file']=None;saved['files']=[];saved['completed']=0
        (self.base/'veo_jobs'/f'{id}.json').write_text(json.dumps(saved))
        http2=FakeHTTP([{'done':True,'response':{'generateVideoResponse':{'generatedSamples':[{'video':{'uri':GOOGLE_API+'/files/video1'}}]}}}])
        resumed=VeoJobs(AIService(self.base,http2),poll_interval=0);resumed.pool.shutdown(wait=True);resumed.pool=SimpleNamespace(submit=lambda fn,id:fn(id))
        self.assertEqual(resumed.get(id)['state'],'paused')
        resumed.resume(id)
        self.assertEqual(resumed.get(id)['state'],'done')
        self.assertFalse(any(method=='POST' for method,_,_ in http2.calls))
        self.assertNotIn('test-google-secret',(self.base/'veo_jobs'/f'{id}.json').read_text())

    def test_github_atomic_snapshot_and_conflict(self):
        not_found=ProviderError('not found');not_found.remote_status=404
        responses=[{'object':{'sha':'head'}},{'tree':{'sha':'base-tree'}},not_found,{'sha':'manifest-blob'},{'sha':'new-tree'},{'sha':'new-commit'},{'ref':'main'}]
        http=FakeHTTP(responses);service=AIService(self.base,http);github=GitHubProjects(service,self.base/'voice')
        result=github.save('project',{'script':'Xin chào'})
        self.assertEqual(result['commit'],'new-commit')
        self.assertFalse(http.calls[-1][2]['json']['force'])
        blob=http.calls[3][2]['json'];manifest=json.loads(base64.b64decode(blob['content']))
        self.assertEqual(manifest['script'],'Xin chào')
        http.responses=[{'object':{'sha':'head'}},{'tree':{'sha':'base-tree'}},{'type':'file','encoding':'base64','content':base64.b64encode(b'{}').decode(),'sha':'different'}]
        with self.assertRaises(ValueError):github.save('project',{'script':'New'},expected_revision='old')
        self.assertEqual(len([c for c in http.calls if c[0]=='POST']),3)

    def test_github_restore_and_path_validation(self):
        original={'version':1,'script':'hello','media':[{'id':'image.png','name':'Picture','url':'https://evil.invalid/image','kind':'image'}],'parts':[]}
        def content(binary,sha='file'):
            return {'type':'file','encoding':'base64','content':base64.b64encode(binary).decode(),'sha':sha}
        http=FakeHTTP([{'object':{'sha':'head'}},content(json.dumps(original).encode(),'rev'),content(b'png')])
        service=AIService(self.base,http);github=GitHubProjects(service,self.base/'voice')
        restored=github.load('p1')['project']
        self.assertTrue(restored['media'][0]['url'].startswith('/assets/'))
        self.assertEqual((service.assets/restored['media'][0]['id']).read_bytes(),b'png')
        with self.assertRaises(ValueError):github.location('../escape')

    @unittest.skipUnless(__import__('shutil').which('ffmpeg'), 'FFmpeg required')
    def test_openai_and_gemini_speech(self):
        buffer=io.BytesIO()
        with wave.open(buffer,'wb') as out:
            out.setnchannels(1);out.setsampwidth(2);out.setframerate(24000);out.writeframes(b'\0\0'*2400)
        encoded=base64.b64encode(buffer.getvalue()).decode()
        http=FakeHTTP([SimpleNamespace(content=b'mp3'),{'steps':[{'type':'model_output','content':[{'type':'audio','mime_type':'audio/wav','data':encoded}]}]}])
        service=AIService(self.base,http)
        service.openai_speech('Hello','alloy',self.base/'openai.mp3')
        service.gemini_speech('Xin chào','Kore',self.base/'gemini.mp3','Vui vẻ')
        self.assertGreater((self.base/'gemini.mp3').stat().st_size,100)
        self.assertEqual(http.calls[1][2]['json']['generation_config']['speech_config'][0]['voice'],'Kore')

    def test_veo_ambiguous_submission_not_retried(self):
        service=AIService(self.base,FakeHTTP([ProviderError('timed out')]))
        jobs=VeoJobs(service);jobs.pool.shutdown(wait=True);jobs.pool=SimpleNamespace(submit=lambda fn,id:fn(id))
        id=jobs.start([{'prompt':'sunrise'}],'16:9','720p')
        self.assertEqual(jobs.get(id)['state'],'error')
        with self.assertRaises(ValueError):jobs.resume(id)
        self.assertEqual(len(service.http.calls),1)

    def test_routes_validation_and_scene_output(self):
        http=FakeHTTP([]);service=AIService(self.base,http);app=Flask(__name__)
        @app.errorhandler(ValueError)
        def invalid(error):return jsonify(ok=False,error=str(error)),400
        jobs=VeoJobs(service);register_ai(app,self.base,self.base/'voice',service,jobs)
        client=app.test_client()
        self.assertEqual(client.post('/api/ai/text',json=[]).status_code,400)
        self.assertEqual(client.post('/api/ai/scenes',json={'script':'hello','count':13}).status_code,400)
        self.assertEqual(client.post('/api/ai/image',json={'prompt':'hello','ratio':'2:3'}).status_code,400)
        self.assertNotIn('test-google-secret',client.get('/api/ai/providers').get_data(as_text=True))
        jobs.pool.shutdown(wait=True)

if __name__=='__main__':unittest.main()
