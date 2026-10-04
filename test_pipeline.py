import io
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from flask import Flask, jsonify
from studio_pipeline import register_pipeline

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class PipelineTests(unittest.TestCase):
    def test_full_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);voices=base/'voices';voices.mkdir()
            subprocess.run(['ffmpeg','-loglevel','error','-y','-f','lavfi','-i','sine=frequency=440:duration=1.2',str(voices/'test.mp3')],check=True)
            subprocess.run(['ffmpeg','-loglevel','error','-y','-f','lavfi','-i','color=c=green:s=100x100','-frames:v','1',str(base/'image.png')],check=True)
            subprocess.run(['ffmpeg','-loglevel','error','-y','-f','lavfi','-i','sine=frequency=220:duration=1.2',str(base/'music.mp3')],check=True)
            app=Flask(__name__)
            @app.errorhandler(ValueError)
            def invalid(error): return jsonify(ok=False,error=str(error)),400
            register_pipeline(app,base,voices);client=app.test_client()
            uploaded=client.post('/api/upload',data={'files':(io.BytesIO((base/'image.png').read_bytes()),'image.png')}).get_json()['files'][0]
            music=client.post('/api/upload',data={'files':(io.BytesIO((base/'music.mp3').read_bytes()),'music.mp3')}).get_json()['files'][0]
            parts=[{'file':'test.mp3','text':'Xin chào thế giới.'}]
            sub=client.post('/api/subtitles',json={'parts':parts}).get_json()
            self.assertIn('-->',sub['srt'])
            with client.post('/api/voice/download-all',json={'parts':parts}) as response:
                self.assertEqual(response.status_code,200)
                self.assertTrue(response.data.startswith(b'PK'))
            result=client.post('/api/export',json={'parts':parts,'media':[uploaded],'music':music,'srt':sub['srt'],'ratio':'9:16','resolution':'720p'})
            self.assertEqual(result.status_code,202)
            job=result.get_json()['job_id']
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                status=client.get('/api/export/'+job).get_json()
                if status['state']!='running': break
                time.sleep(.2)
            self.assertEqual(status['state'],'done',status)
            with client.get(status['url']) as response: self.assertEqual(response.status_code,200)
            probe=subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','csv=p=0',str(base/'studio_exports'/job/'output.mp4')],text=True).strip()
            self.assertEqual(probe,'720,1280')
            self.assertEqual(client.post('/api/subtitles',json={'parts':[{'file':'../test.mp3'}]}).status_code,400)
            self.assertEqual(client.post('/api/upload',data={'files':(io.BytesIO(b'bad'),'bad.exe')}).status_code,400)

    def test_scene_voice_alignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);voices=base/'voices';voices.mkdir()
            for name,length in [('long',1.2),('short',.4)]:
                subprocess.run(['ffmpeg','-loglevel','error','-y','-f','lavfi','-i',f'sine=frequency=440:duration={length}',str(voices/(name+'.mp3'))],check=True)
            subprocess.run(['ffmpeg','-loglevel','error','-y','-f','lavfi','-i','color=c=green:s=100x100','-frames:v','1',str(base/'image.png')],check=True)
            app=Flask(__name__);register_pipeline(app,base,voices);client=app.test_client()
            uploaded=client.post('/api/upload',data={'files':(io.BytesIO((base/'image.png').read_bytes()),'image.png')}).get_json()['files'][0]
            result=client.post('/api/export',json={'parts':[{'file':'long.mp3','scene_index':1},{'file':'short.mp3','scene_index':2}],
                'media':[{**uploaded,'scene_index':1},{**uploaded,'scene_index':2}]})
            self.assertEqual(result.status_code,202)
            job=result.get_json()['job_id'];deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                status=client.get('/api/export/'+job).get_json()
                if status['state']!='running':break
                time.sleep(.2)
            self.assertEqual(status['state'],'done',status)
            def length(filename):
                return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(base/'studio_exports'/job/filename)],text=True))
            self.assertGreater(length('scene_000.mp4'),length('scene_001.mp4')*2)

if __name__=='__main__': unittest.main()
