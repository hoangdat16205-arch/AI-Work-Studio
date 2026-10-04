from flask import jsonify, request
from ai_providers import AIService, ProviderError
from github_projects import GitHubProjects
from veo_jobs import VeoJobs


def register_ai(app, base, voice_dir, service=None, jobs=None):
    service=service or AIService(base)
    jobs=jobs or VeoJobs(service)
    github=GitHubProjects(service,voice_dir)
    app.extensions['studio_ai']={'service':service,'jobs':jobs,'github':github}

    def body():
        data=request.get_json()
        if not isinstance(data,dict):raise ValueError('Dữ liệu phải là JSON object.')
        return data

    def text_field(data,name,limit):
        value=data.get(name,'')
        if not isinstance(value,str) or not 1<=len(value.strip())<=limit:
            raise ValueError(f'{name} cần từ 1 đến {limit} ký tự.')
        return value.strip()

    @app.errorhandler(ProviderError)
    def provider_error(error):
        return jsonify(ok=False,error=str(error)),error.status

    @app.get('/api/ai/providers')
    def providers():
        return jsonify(ok=True,providers=service.status(),github=github.status())

    @app.post('/api/ai/check')
    def check():
        provider=body().get('provider')
        if provider=='github':return jsonify(ok=True,**github.check())
        return jsonify(ok=True,**service.check(provider))

    @app.post('/api/ai/text')
    def generate_text():
        data=body();prompt=text_field(data,'prompt',50000)
        task=data.get('task','script')
        language=str(data.get('language','Tiếng Việt'))[:100]
        systems={
            'script':f'Write a compelling video narration script in {language}. Return only spoken narration, no headings, markup, stage directions or explanation. Follow the requested length and audience.',
            'rewrite':f'Improve this video narration in {language}. Preserve meaning and facts. Return only the improved narration.',
            'translate':f'Translate the supplied narration into {language}. Preserve meaning and tone. Return only the translation.',
            'titles':f'Generate 5 video titles, a concise description and relevant hashtags in {language}. Do not invent facts.',
        }
        if task not in systems:raise ValueError('Tác vụ AI chưa được hỗ trợ.')
        text,model=service.text(data.get('provider'),prompt,systems[task],data.get('model') or None)
        return jsonify(ok=True,text=text,model=model)

    @app.post('/api/ai/scenes')
    def generate_scenes():
        data=body();script=text_field(data,'script',50000)
        count=data.get('count',6)
        if isinstance(count,bool) or not isinstance(count,int) or not 1<=count<=12:raise ValueError('Số cảnh từ 1 đến 12.')
        scenes,model=service.scenes(data.get('provider'),script,count,data.get('model') or None)
        return jsonify(ok=True,scenes=scenes,model=model)

    @app.post('/api/ai/image')
    def generate_image():
        data=body();prompt=text_field(data,'prompt',4000)
        ratio=data.get('ratio','16:9')
        if ratio not in {'16:9','9:16','1:1'}:raise ValueError('Tỷ lệ ảnh không hợp lệ.')
        files,model=service.image(data.get('provider'),prompt,ratio,data.get('model') or None)
        return jsonify(ok=True,files=files,model=model)

    @app.post('/api/ai/video')
    def video():
        data=body()
        id=jobs.start(data.get('scenes'),data.get('ratio','16:9'),data.get('resolution','720p'))
        return jsonify(ok=True,job_id=id),202

    @app.get('/api/ai/video/<id>')
    def video_status(id):
        return jsonify(ok=True,**jobs.get(id))

    @app.post('/api/ai/video/<id>/resume')
    def video_resume(id):
        jobs.resume(id)
        return jsonify(ok=True,job_id=id),202

    @app.post('/api/github/project/load')
    def github_load():
        return jsonify(ok=True,**github.load(body().get('project_id')))

    @app.post('/api/github/project/save')
    def github_save():
        data=body()
        return jsonify(ok=True,**github.save(data.get('project_id'),data.get('project'),data.get('revision')))

    from studio_workbench import register_workbench
    register_workbench(app,base,service)
    if not app.config.get("IS_TENANT"):
        from studio_company import register_company
        register_company(app,base,service)
    return service
