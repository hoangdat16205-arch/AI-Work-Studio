"""Run the official Kilo CLI against one fixed checkout, one mission at a time.

No shell=True, arbitrary command endpoint, --auto, automatic retry or automatic
deployment. Each mission uses a private, loopback-only Kilo server so canceling
the worker does not terminate a user's other Kilo sessions.
"""
import argparse
import json
import os
import queue
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studio_company import sanitize
from tools.company_client import BridgeClient


def resolve_kilo(executable=None):
    candidate=Path(executable or shutil.which('kilo') or '')
    if not str(candidate) or not candidate.is_file():raise ValueError('Chưa tìm thấy Kilo CLI. Cài @kilocode/cli và chạy kilo auth login trước.')
    if candidate.suffix.lower() in {'.cmd','.bat'}:
        # npm's Windows shim launches this JS file. Invoke Node directly to avoid
        # cmd.exe reparsing paths or arguments containing shell metacharacters.
        search=[candidate.parent/'node_modules'/'@kilocode'/'cli'/'bin'/'kilo',candidate.parent.parent/'@kilocode'/'cli'/'bin'/'kilo']
        javascript=next((p for p in search if p.is_file()),None);node=shutil.which('node')
        if not javascript or not node:raise ValueError('Không nhận diện được Windows shim. Cài lại CLI bằng npm hoặc dùng --kilo đường dẫn kilo.exe.')
        return [node,str(javascript)]
    return [str(candidate)]


def verify_cli(command,root):
    version=subprocess.run(command+['--version'],cwd=root,capture_output=True,text=True,timeout=25,check=True).stdout.strip()
    help_text=subprocess.run(command+['run','--help'],cwd=root,capture_output=True,text=True,timeout=25,check=True).stdout
    if not all(flag in help_text for flag in ['--agent','--format','--attach','--file']):raise ValueError('Phiên bản CLI không hỗ trợ giao thức này. Cập nhật @kilocode/cli theo hướng dẫn.')
    return sanitize(version)[:100]


def start_process(command,root,env):
    options={'cwd':root,'env':env,'stdout':subprocess.PIPE,'stderr':subprocess.STDOUT,'text':True,'encoding':'utf-8','errors':'replace','shell':False}
    if os.name=='nt':options['creationflags']=subprocess.CREATE_NEW_PROCESS_GROUP
    else:options['start_new_session']=True
    return subprocess.Popen(command,**options)


def stop_process(process):
    if process is None or process.poll() is not None:return
    if os.name=='nt':
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=10,check=False)
    else:
        try:os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:return
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
    try:process.wait(timeout=5)
    except subprocess.TimeoutExpired:pass


def drain(process,lines):
    try:
        for line in process.stdout:lines.put(sanitize(line.rstrip())[:6000])
    finally:process.stdout.close()


def safe_result(path):
    if not path.is_file():return {'overall':'needs_review','summary':'Kilo kết thúc nhưng chưa có result.json hợp lệ. Xem log và các thay đổi.','tasks':[]}
    if path.stat().st_size>200000:raise ValueError('result.json vượt 200 KB.')
    result=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(result,dict):raise ValueError('result.json phải là object.')
    return result


def run_mission(client,mission,command,worker,version,timeout=1800):
    root=client.root;id=mission['id'];lease=mission['lease'];directory=root/'.ai-company'/'missions'/id
    directory.mkdir(parents=True,exist_ok=True);brief=directory/'request.md';brief.write_text(mission['prompt'],encoding='utf-8')
    runtime=directory/'runtime.json';runtime.write_text(json.dumps({'lease':lease}),encoding='utf-8');runtime.chmod(0o600)
    # A retry starts a new report; old artifacts and event history are preserved.
    final=directory/'result.json'
    if final.exists():final.rename(directory/('result-previous-'+uuid4().hex[:8]+'.json'))
    env=os.environ.copy();env['AI_COMPANY_URL']=client.url;env['KILO_SERVER_PASSWORD']=secrets.token_urlsafe(32);env['KILO_SERVER_USERNAME']='kilo'
    http=client.http.__class__();http.trust_env=False
    lines=queue.Queue(maxsize=500);server=None;runner=None;started=time.monotonic();last_heartbeat=0;last_flush=0;log_bytes=0
    def heartbeat():client.post(id+'/heartbeat',dict(lease=lease,worker=worker,version=version))
    try:
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        server_url=f'http://127.0.0.1:{port}'
        server=start_process(command+['serve','--hostname','127.0.0.1','--port',str(port)],root,env)
        threading.Thread(target=drain,args=(server,lines),daemon=True).start()
        ready=False
        for _ in range(100):
            if server.poll() is not None:raise RuntimeError('Kilo server không khởi động. Kiểm tra CLI/config trong log.')
            try:
                response=http.get(server_url+'/global/health',auth=('kilo',env['KILO_SERVER_PASSWORD']),timeout=1)
                ready=response.ok
            except Exception:pass
            if ready:break
            if time.monotonic()-last_heartbeat>10:heartbeat();last_heartbeat=time.monotonic()
            time.sleep(.25)
        if not ready:raise RuntimeError('Kilo server chưa sẵn sàng sau thời gian khởi động.')
        runner=start_process(command+['run','--attach',server_url,'--dir',str(root),'--agent','ai-manager','--format','json','--file',str(brief),'Thực hiện mission trong tệp đính kèm và gửi đầy đủ báo cáo theo hướng dẫn.'],root,env)
        threading.Thread(target=drain,args=(runner,lines),daemon=True).start()
        with (directory/'events.log').open('a',encoding='utf-8') as log:
            while True:
                now=time.monotonic()
                if now-started>timeout:raise RuntimeError('Hết thời gian worker. Kiểm tra thay đổi trước khi giao lại.')
                if now-last_heartbeat>10:heartbeat();last_heartbeat=now
                messages=[]
                while len(messages)<8:
                    try:messages.append(lines.get_nowait())
                    except queue.Empty:break
                if messages and log_bytes<1000000:
                    output='\n'.join(messages)
                    # Also scrub exact inherited secrets, which may have nonstandard formats.
                    for key,value in env.items():
                        if value and len(value)>8 and any(s in key.upper() for s in ['TOKEN','KEY','SECRET','PASSWORD']):output=output.replace(value,'[REDACTED]')
                    log.write(output+'\n');log.flush();log_bytes+=len(output.encode())
                    if now-last_flush>1:
                        try:client.post(id+'/log',dict(lease=lease,message=output[:12000]))
                        except RuntimeError:pass
                        last_flush=now
                if runner.poll() is not None and lines.empty():break
                time.sleep(.2)
        code=runner.wait();result=safe_result(final)
        return client.post(id+'/finish',dict(lease=lease,exit_code=code,result=result))
    except (OSError,ValueError,RuntimeError,json.JSONDecodeError) as error:
        result={'overall':'needs_review','summary':sanitize(str(error)),'tasks':[]}
        try:return client.post(id+'/finish',dict(lease=lease,exit_code=1,result=result))
        except Exception:print('Mission bị dừng hoặc mất kết nối; kiểm tra board và checkout trước khi chạy lại.');return None
    finally:
        stop_process(runner);stop_process(server);http.close()
        runtime.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description='Cầu nối Công ty AI trên web ↔ Kilo Code CLI.')
    parser.add_argument('--workspace',default=str(Path(__file__).resolve().parents[1]));parser.add_argument('--url',default='http://127.0.0.1:5000')
    parser.add_argument('--kilo',help='Đường dẫn CLI nếu chưa có trong PATH.');parser.add_argument('--once',action='store_true')
    parser.add_argument('--timeout',type=int,default=1800)
    args=parser.parse_args();root=Path(args.workspace).resolve()
    if root!=Path(__file__).resolve().parents[1]:raise ValueError('Worker này chỉ thực thi checkout chứa helper/config. Copy gói cấu hình và helper sang dự án khác trước.')
    if not 30<=args.timeout<=7200:raise ValueError('Timeout phải từ 30 đến 7200 giây.')
    command=resolve_kilo(args.kilo);version=verify_cli(command,root);client=BridgeClient(root,args.url);worker=uuid4().hex
    print(f'Kilo CLI {version}. Worker chờ nhiệm vụ từ web; Ctrl+C để dừng. Không tự retry.')
    try:
        while True:
            response=client.post('claim',dict(worker=worker,version=version))
            if response['mission']:
                print('Đã nhận mission '+response['mission']['id'])
                outcome=run_mission(client,response['mission'],command,worker,version,args.timeout)
                if outcome:print('Mission: '+outcome['mission']['status'])
            if args.once:break
            time.sleep(3)
    finally:client.http.close()


if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:print('Đã dừng worker. Mission chưa có báo cáo sẽ cần kiểm tra trước khi chạy lại.')
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:raise SystemExit(sanitize(str(error)))
