"""Local media, subtitle and video pipeline; FFmpeg must be installed."""
import io
import json
import shutil
import subprocess
import threading
import zipfile
from pathlib import Path
from uuid import uuid4
from flask import request, jsonify, send_file, send_from_directory


def register_pipeline(app, base, voice_dir):
    assets = base / 'studio_assets'
    jobs_dir = base / 'studio_exports'
    assets.mkdir(exist_ok=True)
    jobs_dir.mkdir(exist_ok=True)
    jobs = {}
    app.config['MAX_CONTENT_LENGTH'] = 250 * 1024 * 1024
    extensions = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.mp4', '.mov', '.mkv', '.avi', '.mp3', '.wav', '.m4a', '.ogg'}

    def local_file(name, directory):
        if not isinstance(name, str) or Path(name).name != name:
            raise ValueError('Tên tệp không hợp lệ.')
        path = directory / name
        if not path.is_file():
            raise ValueError('Tệp không còn tồn tại. Hãy tải lại tệp hoặc tạo voice.')
        return path

    def run(args, cwd=None):
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=900)
        if result.returncode:
            app.logger.warning('Media processing failed: %s', result.stderr[-1000:])
            raise ValueError('Không xử lý được media. Kiểm tra định dạng tệp và cài đặt FFmpeg.')
        return result.stdout

    def duration(path):
        return float(run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(path)]).strip())

    def subtitle(parts):
        def timestamp(seconds):
            ms = round(seconds * 1000)
            return f'{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}'
        blocks, elapsed, index = [], 0, 1
        for part in parts:
            length = duration(local_file(part['file'], voice_dir))
            words = str(part.get('text', '')).split()
            groups = [' '.join(words[i:i+12]) for i in range(0, len(words), 12)] or ['…']
            for i, line in enumerate(groups):
                start, end = elapsed + length*i/len(groups), elapsed + length*(i+1)/len(groups)
                blocks.append(f'{index}\n{timestamp(start)} --> {timestamp(end)}\n{line}\n')
                index += 1
            elapsed += length
        return '\n'.join(blocks)

    @app.post('/api/upload')
    def upload():
        files = request.files.getlist('files')
        if not files:
            raise ValueError('Hãy chọn tệp.')
        if any(Path(f.filename or '').suffix.lower() not in extensions for f in files):
            raise ValueError('Định dạng tệp chưa được hỗ trợ.')
        result = []
        for file in files:
            ext = Path(file.filename).suffix.lower()
            name = uuid4().hex + ext
            file.save(assets / name)
            kind = 'image' if ext in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'} else 'audio' if ext in {'.mp3', '.wav', '.m4a', '.ogg'} else 'video'
            result.append({'id': name, 'name': Path(file.filename).name, 'kind': kind, 'url': '/assets/' + name})
        return jsonify(ok=True, files=result)

    @app.get('/assets/<name>')
    def asset(name):
        return send_from_directory(assets, name)

    @app.post('/api/voice/download-all')
    def download_parts():
        data = request.get_json()
        if not isinstance(data, dict) or not data.get('parts'):
            raise ValueError('Chưa có đoạn voice.')
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for i, part in enumerate(data['parts'], 1):
                archive.write(local_file(part['file'], voice_dir), f'voice_part_{i:03d}.mp3')
        buffer.seek(0)
        return send_file(buffer, mimetype='application/zip', as_attachment=True, download_name='voice_parts.zip')

    @app.post('/api/subtitles')
    def subtitles():
        data = request.get_json()
        if not isinstance(data, dict) or not data.get('parts'):
            raise ValueError('Tạo Voice AI trước khi tạo phụ đề.')
        if not shutil.which('ffprobe'):
            raise ValueError('Cần cài FFmpeg và thêm vào PATH.')
        return jsonify(ok=True, srt=subtitle(data['parts']), timing='estimated')

    def render(job_id, data):
        job = jobs[job_id]
        folder = jobs_dir / job_id
        folder.mkdir()
        try:
            parts = data.get('parts', [])
            media = data.get('media', [])
            if not parts or not media:
                raise ValueError('Cần có voice và ít nhất một ảnh/video.')
            audio_files = [local_file(p['file'], voice_dir) for p in parts]
            media_files = [local_file(m['id'], assets) for m in media]
            resolution = data.get('resolution', '720p')
            dimensions = {'720p': {'16:9': (1280,720), '9:16': (720,1280), '1:1': (720,720)},
                          '1080p': {'16:9': (1920,1080), '9:16': (1080,1920), '1:1': (1080,1080)}}
            if resolution not in dimensions or data.get('ratio', '16:9') not in dimensions[resolution]:
                raise ValueError('Tỷ lệ hoặc độ phân giải không hợp lệ.')
            width, height = dimensions[resolution][data.get('ratio', '16:9')]
            job.update(progress=5, message='Đang ghép các đoạn voice')
            normalized = []
            for i, path in enumerate(audio_files):
                name = f'audio_{i:03d}.wav'
                run(['ffmpeg','-y','-i',str(path),'-ar','44100','-ac','1',name], folder)
                normalized.append(name)
            (folder/'audio.txt').write_text('\n'.join(f"file '{n}'" for n in normalized))
            run(['ffmpeg','-y','-f','concat','-safe','0','-i','audio.txt','-c:a','pcm_s16le','voice.wav'], folder)
            total = duration(folder/'voice.wav')
            segments = [total / len(media_files)] * len(media_files)
            media_indices = [m.get('scene_index') for m in media]
            part_indices = list(dict.fromkeys(p.get('scene_index') for p in parts))
            if all(media_indices) and len(set(media_indices)) == len(media_indices) and part_indices == media_indices:
                weights = [sum(duration(folder / normalized[i]) for i,p in enumerate(parts) if p.get('scene_index')==index) for index in media_indices]
                weight_total = sum(weights)
                if weight_total:
                    segments = [total * weight / weight_total for weight in weights]
            video_names = []
            for i, path in enumerate(media_files):
                job.update(progress=10+int(65*i/len(media_files)), message=f'Đang dựng cảnh {i+1}/{len(media_files)}')
                name = f'scene_{i:03d}.mp4'
                input_args = ['-loop','1'] if path.suffix.lower() in {'.png','.jpg','.jpeg','.webp','.bmp'} else ['-stream_loop','-1']
                filter_arg = f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30'
                run(['ffmpeg','-y',*input_args,'-i',str(path),'-t',str(segments[i]),'-vf',filter_arg,'-an','-c:v','libx264','-preset','veryfast','-pix_fmt','yuv420p',name],folder)
                video_names.append(name)
            (folder/'video.txt').write_text('\n'.join(f"file '{n}'" for n in video_names))
            run(['ffmpeg','-y','-f','concat','-safe','0','-i','video.txt','-c','copy','silent.mp4'],folder)
            job.update(progress=80, message='Đang ghép nhạc và phụ đề')
            args = ['ffmpeg','-y','-i','silent.mp4','-i','voice.wav']
            music = data.get('music')
            if music:
                music_path = local_file(music['id'],assets)
                volume = max(0, min(1, float(data.get('music_volume', .15))))
                args += ['-stream_loop','-1','-i',str(music_path),'-filter_complex',f'[2:a]volume={volume}[bg];[1:a][bg]amix=inputs=2:duration=first:normalize=0[mixed]','-map','0:v','-map','[mixed]']
            else:
                args += ['-map','0:v','-map','1:a']
            srt = str(data.get('srt', '')).strip()
            if srt:
                (folder/'subtitles.srt').write_text(srt,encoding='utf-8')
                args += ['-vf',"subtitles=subtitles.srt:force_style='FontSize=20,Outline=2,MarginV=30'",'-c:v','libx264','-preset','veryfast']
            else:
                args += ['-c:v','copy']
            args += ['-c:a','aac','-t',str(total),'-movflags','+faststart','output.mp4']
            run(args,folder)
            job.update(state='done', progress=100, message='Video đã sẵn sàng', url=f'/exports/{job_id}/output.mp4')
        except Exception as error:
            app.logger.exception('Video export failed')
            job.update(state='error', message=str(error) if isinstance(error,ValueError) else 'Xuất video thất bại. Kiểm tra FFmpeg và media.')

    @app.post('/api/export')
    def start_export():
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            raise ValueError('Cần cài FFmpeg và thêm vào PATH để xuất video.')
        data = request.get_json()
        if not isinstance(data,dict) or not data.get('parts') or not data.get('media'):
            raise ValueError('Cần tạo voice và thêm ảnh/video trước.')
        job_id = uuid4().hex
        jobs[job_id] = {'state':'running','progress':0,'message':'Đang chuẩn bị'}
        threading.Thread(target=render,args=(job_id,data),daemon=True).start()
        return jsonify(ok=True, job_id=job_id),202

    @app.get('/api/export/<job_id>')
    def export_status(job_id):
        if job_id not in jobs:
            return jsonify(ok=False,error='Không tìm thấy tác vụ.'),404
        return jsonify(ok=True, **jobs[job_id])

    @app.get('/exports/<job_id>/output.mp4')
    def output(job_id):
        if len(job_id)!=32 or any(c not in '0123456789abcdef' for c in job_id):
            return jsonify(ok=False,error='Tệp không hợp lệ.'),404
        return send_from_directory(jobs_dir/job_id,'output.mp4',as_attachment=True)
