import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('studio', Path(__file__).with_name('AI_Video_Studio_V7_5_Backend_V4Voice.py'))
studio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(studio)

class OriginalHandlerFixture(unittest.TestCase):
    def setUp(self):
        self.configuration=patch.dict(studio.app.config,{'TESTING':True,'AUTH_TEST_BYPASS':True})
        self.configuration.start();self.addCleanup(self.configuration.stop)

class VoiceTests(OriginalHandlerFixture):
    def test_long_script(self):
        for text in ['word ' * 900, 'x' * 1501]:
            parts = studio.split_script(text)
            self.assertTrue(all(0 < len(p) <= 500 for p in parts))
            self.assertEqual(''.join(text.split()), ''.join(''.join(p.split()) for p in parts))

    def test_explicit_elevenlabs(self):
        calls = []
        def convert(**kwargs):
            calls.append(kwargs)
            return [b'mp3']
        client = SimpleNamespace(text_to_speech=SimpleNamespace(convert=convert))
        with tempfile.TemporaryDirectory() as tmp, patch.object(studio, 'eleven_client', client), patch.dict(studio.ELEVENLABS_VOICE_MAP, {'ElevenLabs - Test': 'voice-id'}, clear=True):
            studio.make_voice('Xin chào', 'ElevenLabs - Test', Path(tmp)/'a.mp3', 'Tiếng Việt (Vietnam)')
        self.assertEqual(calls[0]['voice_id'], 'voice-id')
        self.assertEqual(calls[0]['model_id'], 'eleven_flash_v2_5')

    def test_profile_and_emotion(self):
        calls=[]
        class Communicate:
            def __init__(self, **kwargs): calls.append(kwargs)
            async def save(self, filename): Path(filename).write_bytes(b'mp3')
        with tempfile.TemporaryDirectory() as tmp, patch.object(studio.edge_tts, 'Communicate', Communicate):
            studio.make_voice('Hello', 'Việt Nam - Nam trầm', Path(tmp)/'a.mp3', emotion='Nghiêm túc')
        self.assertEqual(calls[0]['voice'], 'vi-VN-NamMinhNeural')
        self.assertEqual(calls[0]['rate'], '-15%')
        self.assertEqual(calls[0]['pitch'], '-8Hz')

    def test_api_isolation_and_validation(self):
        def generate(text, selected, output, *args):
            output.write_bytes(b'mp3')
            return 'voice', 'label'
        with tempfile.TemporaryDirectory() as tmp, patch.object(studio, 'OUTPUT_DIR', Path(tmp)), patch.object(studio, 'make_voice', generate):
            client=studio.app.test_client()
            self.assertEqual(client.post('/api/voice',json=[]).status_code, 400)
            self.assertEqual(client.post('/api/voice',json={'text':''}).status_code, 400)
            a=client.post('/api/voice',json={'text':'hello'}).get_json()
            b=client.post('/api/voice',json={'text':'hello'}).get_json()
            self.assertNotEqual(a['parts'][0]['url'], b['parts'][0]['url'])
            with client.get(a['parts'][0]['url']) as response:
                self.assertEqual(response.data,b'mp3')
            self.assertEqual(client.get('/api/status').status_code,200)

    def test_auto_fallback(self):
        def fail(**kwargs): raise RuntimeError('provider unavailable')
        client=SimpleNamespace(text_to_speech=SimpleNamespace(convert=fail))
        async def edge(text,voice,output,*args): output.write_bytes(b'edge')
        with tempfile.TemporaryDirectory() as tmp, patch.object(studio,'eleven_client',client), patch.dict(studio.ELEVENLABS_VOICE_MAP,{'ElevenLabs - Test':'id'},clear=True), patch.object(studio,'edge_generate',edge):
            output=Path(tmp)/'a.mp3'
            studio.make_voice('Hello world','Tự động',output,'English (United States)')
            self.assertEqual(output.read_bytes(),b'edge')
            with self.assertRaises(RuntimeError): studio.make_voice('Hello','ElevenLabs - Test',output)



class CatalogTests(OriginalHandlerFixture):
    def test_pagination_and_duplicate_names(self):
        pages=[SimpleNamespace(voices=[SimpleNamespace(name='Same',voice_id='one')],has_more=True,next_page_token='next'),SimpleNamespace(voices=[SimpleNamespace(name='Same',voice_id='two')],has_more=False,next_page_token=None)]
        with patch.object(studio,'eleven_client',SimpleNamespace(voices=SimpleNamespace(search=lambda **kwargs: pages.pop(0)))), patch.object(studio,'ELEVENLABS_VOICE_MAP',{}):
            result=studio.load_elevenlabs_voices()
            self.assertEqual(set(result.values()),{'one','two'})
    def test_edge_catalog_visible(self):
        voices=studio.app.test_client().get('/api/voices').get_json()['voices']
        self.assertGreater(len([v for v in voices if v['engine']=='edge_catalog']),300)

if __name__=='__main__': unittest.main()
