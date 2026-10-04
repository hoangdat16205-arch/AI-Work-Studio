"""Read/write project snapshots using GitHub's official Git Data and Contents APIs."""
import base64
import json
import os
import re
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4
from ai_providers import ProviderError

class GitHubProjects:
    def __init__(self, service, voice_dir):
        self.service=service
        self.voice_dir=Path(voice_dir)

    def config(self):
        repo=os.getenv('GITHUB_REPO','')
        if not re.fullmatch(r'[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+',repo):
            raise ValueError('Điền GITHUB_REPO=owner/repository trong .env.')
        branch=os.getenv('GITHUB_BRANCH','main')
        prefix=os.getenv('GITHUB_PROJECTS_PATH','ai-video-studio').strip('/')
        if not prefix or any(p in {'','..','.'} for p in prefix.split('/')):
            raise ValueError('GITHUB_PROJECTS_PATH không hợp lệ.')
        headers={'Authorization':'Bearer '+self.service.key('GITHUB_TOKEN'),'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}
        return 'https://api.github.com/repos/'+repo,branch,prefix,headers

    def call(self,method,path,**kwargs):
        base,_,_,headers=self.config()
        return self.service.http.json(method,base+path,headers=headers,**kwargs)

    def status(self):
        return {'configured':bool(os.getenv('GITHUB_TOKEN') and os.getenv('GITHUB_REPO')),
                'repo':os.getenv('GITHUB_REPO',''),'branch':os.getenv('GITHUB_BRANCH','main')}

    def check(self):
        result=self.call('GET','')
        return {'repo':result.get('full_name'),'can_write':result.get('permissions',{}).get('push',False)}

    def location(self,id):
        if not isinstance(id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',id):
            raise ValueError('Mã dự án chỉ gồm chữ, số, gạch ngang/gạch dưới (tối đa 64 ký tự).')
        _,_,prefix,_=self.config()
        return prefix+'/'+id

    def content(self,path,ref=None):
        _,branch,_,_=self.config()
        result=self.call('GET','/contents/'+quote(path,safe='/'),params={'ref':ref or branch})
        if not isinstance(result,dict) or result.get('type')!='file':
            raise ProviderError('Tệp GitHub không thuộc định dạng snapshot được hỗ trợ.')
        sha=result['sha']
        if result.get('size',0)>5*1024*1024:raise ValueError('Tệp GitHub vượt 5 MB.')
        if result.get('encoding')=='none':
            result=self.call('GET','/git/blobs/'+sha)
        if result.get('encoding')!='base64':raise ProviderError('Encoding GitHub chưa được hỗ trợ.')
        try:
            binary=base64.b64decode(result['content'])
        except (KeyError,ValueError):
            raise ProviderError('Không đọc được tệp GitHub.') from None
        if len(binary)>5*1024*1024:
            raise ValueError('Tệp GitHub vượt 5 MB.')
        return binary,sha

    def save(self,id,project,expected_revision=None):
        location=self.location(id)
        if not isinstance(project,dict) or not isinstance(project.get('script',''),str) or len(project.get('script',''))>50000:
            raise ValueError('Dữ liệu dự án không hợp lệ.')
        # Preflight every file before making any GitHub write.
        files={}
        references=[]
        for item in project.get('media',[]):references.append((item,self.service.assets,'assets'))
        if project.get('music'):references.append((project['music'],self.service.assets,'assets'))
        for part in project.get('parts',[]):references.append((part,self.voice_dir,'voice'))
        if len(references)>100:raise ValueError('Tối đa 100 tài nguyên trong một snapshot GitHub.')
        manifest={'version':1,'script':project.get('script',''),'srt':str(project.get('srt',''))[:300000],
                  'scenes':project.get('scenes',[]),'media':project.get('media',[]),'music':project.get('music'),
                  'parts':project.get('parts',[]),'settings':project.get('settings'),
                  'ratio':project.get('ratio','16:9'),'resolution':project.get('resolution','720p'),
                  'music_volume':project.get('music_volume',.15),'workspace':project.get('workspace',{})}
        for item,directory,kind in references:
            name=item.get('file') if kind=='voice' else item.get('id')
            if not isinstance(name,str) or Path(name).name!=name or not re.fullmatch(r'[A-Za-z0-9_.-]+',name):
                raise ValueError('Tên tài nguyên dự án không hợp lệ.')
            if Path(name).suffix.lower() not in {'.png','.jpg','.jpeg','.webp','.bmp','.mp4','.mov','.mkv','.avi','.mp3','.wav','.m4a','.ogg'}:
                raise ValueError('Không đồng bộ loại tệp này lên GitHub.')
            path=directory/name
            if not path.is_file():raise ValueError('Một tài nguyên đã bị xóa trên máy backend.')
            if path.stat().st_size>5*1024*1024:raise ValueError(f'Tệp {name} vượt 5 MB. Dùng tệp nhỏ hơn khi lưu vào GitHub.')
            files[f'{location}/{kind}/{name}']=path.read_bytes()
        files[location+'/project.json']=json.dumps(manifest,ensure_ascii=False).encode('utf-8')
        if sum(len(b) for b in files.values())>20*1024*1024:raise ValueError('Snapshot vượt 20 MB. Giảm tài nguyên trước khi lưu GitHub.')
        _,branch,_,_=self.config()
        head=self.call('GET','/git/ref/heads/'+quote(branch,safe=''))['object']['sha']
        commit=self.call('GET','/git/commits/'+head)
        try:
            _,current_revision=self.content(location+'/project.json',ref=head)
        except ProviderError as error:
            if getattr(error,'remote_status',None)!=404:raise
            current_revision=None
        if current_revision!=expected_revision:
            raise ValueError('Dự án đã tồn tại hoặc đã đổi trên GitHub. Bấm Tải dự án trước khi lưu để tránh ghi đè thay đổi chưa đọc.')
        entries=[]
        manifest_sha=None
        for path,binary in files.items():
            blob=self.call('POST','/git/blobs',json={'content':base64.b64encode(binary).decode('ascii'),'encoding':'base64'})
            entries.append({'path':path,'mode':'100644','type':'blob','sha':blob['sha']})
            if path.endswith('/project.json'):manifest_sha=blob['sha']
        tree=self.call('POST','/git/trees',json={'base_tree':commit['tree']['sha'],'tree':entries})
        new_commit=self.call('POST','/git/commits',json={'message':f'AI Video Studio: save project {id}','tree':tree['sha'],'parents':[head]})
        # Fast-forward only: concurrent or protected branch changes fail without forcing history.
        self.call('PATCH','/git/refs/heads/'+quote(branch,safe=''),json={'sha':new_commit['sha'],'force':False})
        return {'revision':manifest_sha,'commit':new_commit['sha'],'file_count':len(files)}

    def load(self,id):
        location=self.location(id)
        _,branch,_,_=self.config()
        head=self.call('GET','/git/ref/heads/'+quote(branch,safe=''))['object']['sha']
        binary,revision=self.content(location+'/project.json',ref=head)
        try:project=json.loads(binary)
        except ValueError:raise ProviderError('Snapshot GitHub không phải JSON hợp lệ.') from None
        if not isinstance(project,dict) or project.get('version')!=1 or not isinstance(project.get('script',''),str) or len(project.get('script',''))>50000:
            raise ValueError('Snapshot GitHub không được hỗ trợ.')
        # Never reuse paths/URLs from the remote snapshot: fetch within the selected project and allocate local IDs.
        cache={};total=0
        def restore(item,kind):
            nonlocal total
            if not isinstance(item,dict):raise ValueError('Tài nguyên trong snapshot không hợp lệ.')
            old=item.get('file') if kind=='voice' else item.get('id')
            if not isinstance(old,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+',old):raise ValueError('Đường dẫn snapshot không hợp lệ.')
            ext=Path(old).suffix.lower()
            allowed={'.mp3'} if kind=='voice' else {'.png','.jpg','.jpeg','.webp','.bmp','.mp4','.mov','.mkv','.avi','.mp3','.wav','.m4a','.ogg'}
            if ext not in allowed:raise ValueError('Định dạng tài nguyên không được hỗ trợ.')
            key=(kind,old)
            if key not in cache:
                content,_=self.content(location+'/'+kind+'/'+old,ref=head)
                total+=len(content)
                if total>20*1024*1024:raise ValueError('Snapshot vượt 20 MB.')
                new=uuid4().hex+ext
                directory=self.voice_dir if kind=='voice' else self.service.assets
                directory.mkdir(exist_ok=True)
                (directory/new).write_bytes(content)
                cache[key]=new
            new=cache[key]
            if kind=='voice':return {**item,'file':new,'url':'/audio/'+new}
            detected='image' if ext in {'.png','.jpg','.jpeg','.webp','.bmp'} else 'audio' if ext in {'.mp3','.wav','.m4a','.ogg'} else 'video'
            return {**item,'id':new,'kind':detected,'url':'/assets/'+new}
        if len(project.get('media',[]))+len(project.get('parts',[]))>100:raise ValueError('Snapshot có quá nhiều tài nguyên.')
        project['media']=[restore(item,'assets') for item in project.get('media',[])]
        project['parts']=[restore(item,'voice') for item in project.get('parts',[])]
        project['music']=restore(project['music'],'assets') if project.get('music') else None
        project['srt']=str(project.get('srt',''))[:300000]
        return {'project':project,'revision':revision}
