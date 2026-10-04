"""Official provider APIs. Keys stay on the backend; never returned to the UI."""
import base64
import binascii
import json
import os
import re
import ssl
from pathlib import Path
from urllib.parse import quote, urlparse
from uuid import uuid4
import requests

GOOGLE_API = 'https://generativelanguage.googleapis.com/v1beta'
PROVIDERS = {
    'openai': ('OpenAI', 'OPENAI_API_KEY', 'OPENAI_MODEL', 'gpt-4.1-mini'),
    'gemini': ('Google Gemini', 'GEMINI_API_KEY', 'GEMINI_MODEL', 'gemini-3.8-flash'),
    'claude': ('Anthropic Claude', 'ANTHROPIC_API_KEY', 'CLAUDE_MODEL', 'claude-sonnet-4-6'),
}

class ProviderError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status

class OfficialHTTP:
    def __init__(self):
        self.session = requests.Session()
        # Preserve injected proxy/CA configuration, otherwise use the OS CA bundle.
        self.verify = os.getenv('REQUESTS_CA_BUNDLE') or os.getenv('SSL_CERT_FILE') or ssl.get_default_verify_paths().cafile or True

    def request(self, method, url, **kwargs):
        try:
            kwargs.setdefault('allow_redirects', False)
            response = self.session.request(method, url, timeout=(15, 180), verify=self.verify, **kwargs)
        except requests.Timeout:
            raise ProviderError('Nhà cung cấp phản hồi quá chậm. Yêu cầu có thể đã được xử lý; kiểm tra tài khoản trước khi gọi lại.', 504) from None
        except requests.RequestException:
            raise ProviderError('Không kết nối được API. Kiểm tra mạng, proxy và chứng chỉ TLS.') from None
        if not response.ok:
            status = response.status_code
            messages = {
                400: 'Yêu cầu không được nhà cung cấp chấp nhận. Kiểm tra model, tham số hoặc nội dung.',
                401: 'API key hoặc token không hợp lệ.', 403: 'Tài khoản chưa có quyền gọi API/model hoặc chưa bật thanh toán.',
                404: 'Không tìm thấy model/tài nguyên. Kiểm tra model và quyền truy cập.',
                409: 'Dữ liệu đã thay đổi trên GitHub. Tải lại trước khi lưu.',
                422: 'Không cập nhật được GitHub. Kiểm tra branch, quyền ghi hoặc thay đổi đồng thời.',
                429: 'Đã chạm quota hoặc giới hạn tốc độ. Kiểm tra tài khoản nhà cung cấp.',
            }
            error = ProviderError(messages.get(status, f'Nhà cung cấp trả lỗi HTTP {status}.'), 502)
            error.remote_status = status
            raise error
        return response

    def json(self, method, url, **kwargs):
        response = self.request(method, url, **kwargs)
        try:
            return response.json()
        except ValueError:
            raise ProviderError('API trả dữ liệu không hợp lệ.') from None

    def video_download(self, uri, key, destination):
        # Only official Google hosts may serve Veo output. Never forward a key to another host.
        for _ in range(6):
            parsed = urlparse(uri)
            host = parsed.hostname or ''
            allowed = host in {'generativelanguage.googleapis.com', 'storage.googleapis.com'} or host.endswith('.googleusercontent.com')
            if parsed.scheme != 'https' or not allowed or parsed.username or parsed.password:
                raise ProviderError('Đường dẫn video không thuộc máy chủ Google được hỗ trợ.')
            headers = {'x-goog-api-key': key} if host == 'generativelanguage.googleapis.com' else {}
            response = self.request('GET', uri, headers=headers, stream=True, allow_redirects=False)
            if response.is_redirect:
                from urllib.parse import urljoin
                uri = urljoin(uri, response.headers.get('Location', ''))
                response.close()
                continue
            try:
                size = 0
                with open(destination, 'wb') as file:
                    for chunk in response.iter_content(1024*1024):
                        size += len(chunk)
                        if size > 150*1024*1024:
                            raise ProviderError('Clip quá lớn (giới hạn 150 MB).')
                        file.write(chunk)
                if not size:
                    raise ProviderError('Google trả về video rỗng.')
                return
            except Exception:
                destination.unlink(missing_ok=True)
                raise
            finally:
                response.close()
        raise ProviderError('Đường dẫn tải video chuyển hướng quá nhiều lần.')

class AIService:
    def __init__(self, base, http=None):
        self.base = Path(base)
        self.assets = self.base / 'studio_assets'
        self.assets.mkdir(exist_ok=True)
        self.http = http or OfficialHTTP()

    @staticmethod
    def key(variable):
        value = os.getenv(variable, '').strip()
        if not value:
            raise ProviderError(f'Chưa cấu hình {variable} trong .env. Thêm key rồi khởi động lại backend.', 400)
        return value

    @staticmethod
    def model(value):
        if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9._:-]{1,100}', value):
            raise ValueError('Model ID không hợp lệ.')
        return value

    def status(self):
        result = []
        for id, (label, key, model, default) in PROVIDERS.items():
            result.append({'id': id, 'label': label, 'configured': bool(os.getenv(key)), 'model': os.getenv(model, default),
                           'capabilities': ['text', 'scenes'] + (['image'] if id in {'openai','gemini'} else []), 'key_variable': key})
        result.append({'id':'veo', 'label':'Google Veo', 'configured':bool(os.getenv('GEMINI_API_KEY')),
                       'model':os.getenv('VEO_MODEL','veo-3.1-generate-preview'), 'capabilities':['video'], 'key_variable':'GEMINI_API_KEY'})
        from self_hosted_ai import SelfHostedText
        result.append(SelfHostedText(self.http).status())
        return result

    def check(self, provider):
        if provider=='self_hosted':
            from self_hosted_ai import SelfHostedText
            return SelfHostedText(self.http).check()
        if provider in {'gemini', 'veo'}:
            model = self.model(os.getenv('VEO_MODEL','veo-3.1-generate-preview') if provider=='veo' else os.getenv('GEMINI_MODEL','gemini-3.8-flash'))
            self.http.json('GET', f'{GOOGLE_API}/models/{model}', headers={'x-goog-api-key':self.key('GEMINI_API_KEY')})
        elif provider == 'openai':
            model = self.model(os.getenv('OPENAI_MODEL','gpt-4.1-mini'))
            self.http.json('GET', 'https://api.openai.com/v1/models/'+model, headers={'Authorization':'Bearer '+self.key('OPENAI_API_KEY')})
        elif provider == 'claude':
            model = self.model(os.getenv('CLAUDE_MODEL','claude-sonnet-4-6'))
            self.http.json('GET','https://api.anthropic.com/v1/models/'+model,headers={'x-api-key':self.key('ANTHROPIC_API_KEY'),'anthropic-version':'2023-06-01'})
        else:
            raise ValueError('Nhà cung cấp không được hỗ trợ.')
        return {'message': 'API key và quyền đọc model đã được xác nhận. Quota tạo nội dung được kiểm tra khi thực hiện yêu cầu.'}

    @staticmethod
    def google_output(data):
        """Interactions returns model_output steps; support earlier outputs and generateContent too."""
        output = list(data.get('outputs') or [])
        for step in data.get('steps') or []:
            if step.get('type') == 'model_output':
                content = step.get('content') or []
                output.extend(content if isinstance(content, list) else [content])
        for candidate in data.get('candidates', []):
            output.extend(candidate.get('content', {}).get('parts', []))
        return output

    def text(self, provider, prompt, system, model=None):
        if provider=='self_hosted':
            from self_hosted_ai import SelfHostedText
            return SelfHostedText(self.http).text(prompt,system,model)
        if provider not in PROVIDERS:
            raise ValueError('Chọn OpenAI, Gemini, Claude hoặc AI riêng.')
        _, key_var, model_var, default = PROVIDERS[provider]
        key = self.key(key_var)
        model = self.model(model or os.getenv(model_var,default))
        if provider == 'openai':
            data = self.http.json('POST','https://api.openai.com/v1/responses',headers={'Authorization':'Bearer '+key},
                json={'model':model,'instructions':system,'input':prompt,'max_output_tokens':8000,'store':False})
            text = '\n'.join(c.get('text','') for item in data.get('output',[]) if item.get('type')=='message' for c in item.get('content',[]) if c.get('type')=='output_text')
        elif provider == 'claude':
            data = self.http.json('POST','https://api.anthropic.com/v1/messages',headers={'x-api-key':key,'anthropic-version':'2023-06-01'},
                json={'model':model,'system':system,'max_tokens':8000,'messages':[{'role':'user','content':prompt}]})
            text = '\n'.join(c.get('text','') for c in data.get('content',[]) if c.get('type')=='text')
        else:
            mode = os.getenv('GEMINI_API_MODE','interactions')
            if mode == 'generate_content':
                data = self.http.json('POST',f'{GOOGLE_API}/models/{model}:generateContent',headers={'x-goog-api-key':key},
                    json={'systemInstruction':{'parts':[{'text':system}]},'contents':[{'role':'user','parts':[{'text':prompt}]}],'generationConfig':{'maxOutputTokens':8000}})
            else:
                data = self.http.json('POST',f'{GOOGLE_API}/interactions',headers={'x-goog-api-key':key},
                    json={'model':model,'system_instruction':system,'input':prompt,'store':False})
            text = '\n'.join(c.get('text','') for c in self.google_output(data) if 'text' in c and c.get('type') in {None,'text'})
        if not text.strip():
            raise ProviderError('Model không trả nội dung văn bản. Có thể nội dung bị lọc hoặc model không hỗ trợ tác vụ.')
        if len(text) > 50000:
            raise ProviderError('Kết quả vượt 50.000 ký tự. Hãy giảm độ dài yêu cầu.')
        return text.strip(), model

    def scenes(self, provider, script, count, model=None):
        instruction = ('You are a video storyboard editor. Return ONLY valid JSON with a scenes array. '
            'Each scene must have narration (preserve the original script words and their order), prompt (an English cinematic video prompt), '
            'and title (short Vietnamese title). Distribute ALL narration across scenes without summarizing or omitting it. '
            'Prompts describe camera, subject, action, setting and lighting; no on-screen text. Maintain character and visual continuity.')
        text, model = self.text(provider,f'Chia kịch bản sau thành đúng {count} cảnh, mỗi clip 8 giây:\n\n{script}',instruction,model)
        cleaned = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip())
        try:
            data = json.loads(cleaned)
            scenes = data['scenes']
            if not isinstance(scenes,list) or len(scenes)!=count:
                raise ValueError()
            for index, scene in enumerate(scenes,1):
                if not isinstance(scene,dict) or not isinstance(scene.get('prompt'),str) or not scene['prompt'].strip() or len(scene['prompt'])>4000:
                    raise ValueError()
                if not isinstance(scene.get('narration'),str) or not scene['narration'].strip() or len(scene['narration'])>50000:
                    raise ValueError()
                scene['title'] = str(scene.get('title',f'Cảnh {index}'))[:150]
                scene['index'],scene['duration'] = index,8
            # Do not silently use a storyboard that changed or dropped narration.
            normalize = lambda s: re.sub(r'\W+', '', s).casefold()
            if normalize(' '.join(s['narration'] for s in scenes)) != normalize(script):
                raise ProviderError('AI đã thay đổi/bỏ lời thoại khi chia cảnh. Hãy thử lại hoặc chia cảnh thủ công.')
        except (ValueError,KeyError,TypeError):
            raise ProviderError('AI chưa trả cấu trúc cảnh hợp lệ. Hãy thử lại hoặc giảm số cảnh.') from None
        return scenes,model

    def save_inline(self, encoded, mime, name):
        suffix = {'image/png':'.png','image/jpeg':'.jpg','image/webp':'.webp'}.get(mime)
        if not suffix:
            raise ProviderError('Định dạng ảnh trả về chưa được hỗ trợ.')
        try:
            binary = base64.b64decode(encoded,validate=True)
        except (ValueError,binascii.Error):
            raise ProviderError('API trả ảnh không hợp lệ.') from None
        if not binary or len(binary)>25*1024*1024:
            raise ProviderError('Ảnh rỗng hoặc vượt giới hạn 25 MB.')
        file_id = uuid4().hex+suffix
        (self.assets/file_id).write_bytes(binary)
        return {'id':file_id,'name':name+suffix,'kind':'image','url':'/assets/'+file_id}

    def image(self, provider, prompt, ratio, model=None):
        if provider == 'openai':
            model=self.model(model or os.getenv('OPENAI_IMAGE_MODEL','gpt-image-1'))
            size={'16:9':'1536x1024','9:16':'1024x1536','1:1':'1024x1024'}[ratio]
            data=self.http.json('POST','https://api.openai.com/v1/images/generations',headers={'Authorization':'Bearer '+self.key('OPENAI_API_KEY')},
                               json={'model':model,'prompt':prompt,'size':size,'n':1,'output_format':'png'})
            images=[self.save_inline(item['b64_json'],'image/png','OpenAI image') for item in data.get('data',[]) if item.get('b64_json')]
        elif provider == 'gemini':
            model=self.model(model or os.getenv('GEMINI_IMAGE_MODEL','gemini-3.1-flash-image'))
            key=self.key('GEMINI_API_KEY')
            if os.getenv('GEMINI_API_MODE','interactions')=='generate_content':
                data=self.http.json('POST',f'{GOOGLE_API}/models/{model}:generateContent',headers={'x-goog-api-key':key},
                    json={'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'responseModalities':['TEXT','IMAGE'],'imageConfig':{'aspectRatio':ratio}}})
            else:
                data=self.http.json('POST',f'{GOOGLE_API}/interactions',headers={'x-goog-api-key':key},
                    json={'model':model,'input':prompt,'store':False,'response_format':{'type':'image','aspect_ratio':ratio}})
            images=[]
            for part in self.google_output(data):
                inline=part.get('inlineData') or part.get('inline_data')
                if inline:
                    images.append(self.save_inline(inline['data'],inline.get('mimeType') or inline.get('mime_type'),'Gemini image'))
                elif part.get('type')=='image' and part.get('data'):
                    images.append(self.save_inline(part['data'],part.get('mime_type','image/png'),'Gemini image'))
        else:
            raise ValueError('Tạo ảnh hỗ trợ OpenAI và Gemini.')
        if not images:
            raise ProviderError('API không trả ảnh. Kiểm tra model và nội dung prompt.')
        return images,model

    def openai_speech(self, text, voice, destination, emotion='Tự nhiên'):
        allowed={'alloy','ash','ballad','coral','echo','fable','nova','onyx','sage','shimmer','verse','marin','cedar'}
        if voice not in allowed:
            raise ValueError('Giọng OpenAI không hợp lệ.')
        model=self.model(os.getenv('OPENAI_TTS_MODEL','gpt-4o-mini-tts'))
        payload={'model':model,'input':text,'voice':voice,'response_format':'mp3'}
        if model=='gpt-4o-mini-tts':
            payload['instructions']=f'Read naturally in the language of the input. Requested tone: {emotion}.'
        response=self.http.request('POST','https://api.openai.com/v1/audio/speech',headers={'Authorization':'Bearer '+self.key('OPENAI_API_KEY')},json=payload)
        if not response.content:
            raise ProviderError('OpenAI trả âm thanh rỗng.')
        destination.write_bytes(response.content)
        return voice,'OpenAI • '+voice

    def gemini_speech(self, text, voice, destination, emotion='Tự nhiên'):
        if voice not in GEMINI_TTS_VOICES:
            raise ValueError('Giọng Gemini không hợp lệ.')
        import shutil,subprocess
        if not shutil.which('ffmpeg'):
            raise ValueError('Giọng Gemini cần FFmpeg trong PATH để lưu MP3.')
        model=self.model(os.getenv('GEMINI_TTS_MODEL','gemini-3.8-flash-tts'))
        part={'type':'text','text':text}
        if emotion!='Tự động theo lời thoại':
            part['annotations']=[{'type':'speech_metadata','style':emotion}]
        data=self.http.json('POST',f'{GOOGLE_API}/interactions',headers={'x-goog-api-key':self.key('GEMINI_API_KEY')},
            json={'model':model,'input':[{'type':'user_input','content':[part]}],
                  'response_format':{'type':'audio'},'generation_config':{'speech_config':[{'voice':voice}]},'store':False})
        audio=next((p for p in reversed(self.google_output(data)) if p.get('type')=='audio' and p.get('data')),None)
        if not audio:raise ProviderError('Gemini không trả âm thanh. Kiểm tra model TTS và quyền tài khoản.')
        try:binary=base64.b64decode(audio['data'],validate=True)
        except (ValueError,binascii.Error):raise ProviderError('Dữ liệu âm thanh Gemini không hợp lệ.') from None
        if not binary or len(binary)>25*1024*1024:raise ProviderError('Âm thanh rỗng hoặc quá lớn.')
        args=['ffmpeg','-y']
        mime=audio.get('mime_type','audio/wav')
        if mime.startswith(('audio/L16','audio/pcm')):
            args+=['-f','s16le','-ar','24000','-ac','1']
        args+=['-i','pipe:0','-c:a','libmp3lame','-b:a','128k',str(destination)]
        result=subprocess.run(args,input=binary,capture_output=True,timeout=60)
        if result.returncode:
            destination.unlink(missing_ok=True)
            raise ProviderError('Không chuyển được âm thanh Gemini sang MP3.')
        return voice,'Gemini • '+voice

GEMINI_TTS_VOICES = ['Zephyr','Puck','Charon','Kore','Fenrir','Leda','Orus','Aoede','Callirrhoe','Autonoe',
    'Enceladus','Iapetus','Umbriel','Algieba','Despina','Erinome','Algenib','Rasalgethi','Laomedeia','Achernar',
    'Alnilam','Schedar','Gacrux','Pulcherrima','Achird','Zubenelgenubi','Vindemiatrix','Sadachbia','Sadaltager','Sulafat']
