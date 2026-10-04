"""Durable Veo batches. Resume saved operations without submitting completed scenes twice."""
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
from ai_providers import GOOGLE_API, ProviderError

class VeoJobs:
    def __init__(self, service, poll_interval=10):
        self.service=service
        self.directory=service.base/'veo_jobs'
        self.directory.mkdir(exist_ok=True)
        self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='veo')
        self.lock=threading.RLock()
        self.interval=poll_interval
        self.jobs={}
        for path in self.directory.glob('*.json'):
            try:
                job=json.loads(path.read_text(encoding='utf-8'))
                if job['state']=='running':
                    job['state']='paused'
                    job['message']='Backend đã khởi động lại. Bấm Tiếp tục để lấy kết quả từ operation đã lưu.'
                self.jobs[job['id']]=job
            except (OSError,ValueError,KeyError):
                continue

    def save(self,job):
        temporary=self.directory/(job['id']+'.tmp')
        temporary.write_text(json.dumps(job,ensure_ascii=False),encoding='utf-8')
        temporary.replace(self.directory/(job['id']+'.json'))

    def get(self,id):
        with self.lock:
            if id not in self.jobs:
                raise ValueError('Không tìm thấy tác vụ Veo.')
            job=self.jobs[id]
            return {k:v for k,v in job.items() if k not in {'model','ratio','resolution'}}

    def start(self, scenes, ratio, resolution):
        self.service.key('GEMINI_API_KEY')
        if not isinstance(scenes,list) or not 1<=len(scenes)<=12:
            raise ValueError('Chọn từ 1 đến 12 cảnh mỗi lượt.')
        if ratio not in {'16:9','9:16'} or resolution not in {'720p','1080p'}:
            raise ValueError('Veo hỗ trợ 16:9 hoặc 9:16; 720p hoặc 1080p.')
        from os import getenv
        model=self.service.model(getenv('VEO_MODEL','veo-3.1-generate-preview'))
        items=[]
        for i,scene in enumerate(scenes,1):
            if not isinstance(scene,dict) or not isinstance(scene.get('prompt'),str) or not 1<=len(scene['prompt'].strip())<=4000:
                raise ValueError('Mỗi cảnh cần prompt từ 1 đến 4.000 ký tự.')
            items.append({'index':scene.get('index',i),'order':i,'prompt':scene['prompt'].strip(),'title':str(scene.get('title',f'Cảnh {i}'))[:150],
                          'narration':str(scene.get('narration',''))[:50000],'state':'pending','operation':None,'file':None})
        if any(not isinstance(s['index'],int) or isinstance(s['index'],bool) or not 1<=s['index']<=12 for s in items) or len({s['index'] for s in items})!=len(items):
            raise ValueError('Số thứ tự cảnh phải khác nhau và từ 1 đến 12.')
        with self.lock:
            if sum(j['state']=='running' for j in self.jobs.values())>=2:
                raise ValueError('Đang có hai tác vụ Veo. Chờ một tác vụ hoàn tất.')
            id=uuid4().hex
            job={'id':id,'state':'running','message':'Đang chuẩn bị các cảnh','scenes':items,'files':[],
                 'model':model,'ratio':ratio,'resolution':resolution,'completed':0,'total':len(items)}
            self.jobs[id]=job
            self.save(job)
        self.pool.submit(self.process,id)
        return id

    def resume(self,id):
        with self.lock:
            if id not in self.jobs:raise ValueError('Không tìm thấy tác vụ.')
            job=self.jobs[id]
            if job['state'] not in {'paused','error'}:raise ValueError('Tác vụ này không cần tiếp tục.')
            if any(scene['state']=='submitting' for scene in job['scenes']):
                raise ValueError('Một yêu cầu gửi Google chưa được xác nhận. Kiểm tra tài khoản Google trước khi tạo lại cảnh để tránh gửi trùng.')
            if sum(j['state']=='running' for j in self.jobs.values())>=2:raise ValueError('Đã có hai tác vụ Veo đang chạy.')
            job['state']='running'
            self.save(job)
        self.pool.submit(self.process,id)

    def process(self,id):
        job=self.jobs[id]
        try:
            key=self.service.key('GEMINI_API_KEY')
            for scene in job['scenes']:
                if scene['state']=='done':continue
                if scene['state']=='submitting':raise ProviderError('Không xác định được kết quả yêu cầu đã gửi. Kiểm tra Google trước khi tạo lại cảnh.')
                with self.lock:
                    job['message']=f"Đang tạo cảnh {scene.get('order',scene['index'])}/{job['total']}"
                    self.save(job)
                if not scene['operation']:
                    with self.lock:
                        scene['state']='submitting'
                        self.save(job)
                    response=self.service.http.json('POST',f"{GOOGLE_API}/models/{job['model']}:predictLongRunning",
                        headers={'x-goog-api-key':key},json={'instances':[{'prompt':scene['prompt']}],
                        'parameters':{'aspectRatio':job['ratio'],'durationSeconds':8,'resolution':job['resolution']}})
                    operation=response.get('name','')
                    if not isinstance(operation,str) or not re.fullmatch(r'(?:models/[a-zA-Z0-9._-]+/)?operations/[a-zA-Z0-9._-]+',operation):
                        raise ProviderError('Google chưa trả operation hợp lệ. Kiểm tra tài khoản trước khi thử lại.')
                    with self.lock:
                        scene['operation']=operation
                        scene['state']='waiting'
                        self.save(job)
                deadline=time.monotonic()+1200
                while True:
                    result=self.service.http.json('GET',f"{GOOGLE_API}/{scene['operation']}",headers={'x-goog-api-key':key})
                    if result.get('done'):break
                    if time.monotonic()>deadline:
                        raise ProviderError('Google vẫn đang tạo clip sau 20 phút. Operation đã lưu; dùng Tiếp tục để kiểm tra mà không gửi lại prompt.')
                    time.sleep(self.interval)
                if result.get('error'):
                    raise ProviderError('Google báo lỗi tạo clip. Kiểm tra model, quota hoặc nội dung trong tài khoản Google.')
                samples=result.get('response',{}).get('generateVideoResponse',{}).get('generatedSamples',[])
                if not samples or not samples[0].get('video',{}).get('uri'):
                    raise ProviderError('Google không trả clip; nội dung có thể bị lọc. Các clip trước vẫn được giữ.')
                filename=uuid4().hex+'.mp4'
                self.service.http.video_download(samples[0]['video']['uri'],key,self.service.assets/filename)
                item={'id':filename,'name':scene['title']+'.mp4','kind':'video','url':'/assets/'+filename,'scene_index':scene['index']}
                with self.lock:
                    scene['state']='done'
                    scene['file']=item
                    job['files'].append(item)
                    job['completed']=len(job['files'])
                    self.save(job)
            with self.lock:
                job.update(state='done',message='Các clip Veo đã sẵn sàng để dựng video.')
                self.save(job)
        except Exception as error:
            with self.lock:
                job['state']='error'
                job['message']=str(error) if isinstance(error,(ProviderError,ValueError)) else 'Không hoàn tất tác vụ Veo. Các clip đã tạo được giữ lại.'
                self.save(job)
