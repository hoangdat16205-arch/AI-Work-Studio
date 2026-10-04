"""Shared local bridge client. Credentials never appear in CLI arguments."""
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse
import requests


class BridgeClient:
    def __init__(self,root,url=None):
        self.root=Path(root).resolve();self.url=(url or os.getenv('AI_COMPANY_URL','http://127.0.0.1:5000')).rstrip('/')
        from dotenv import load_dotenv
        load_dotenv(self.root/'.env')
        self.data_root=Path(os.getenv('STUDIO_DATA_ROOT') or str(self.root)).resolve()
        parsed=urlparse(self.url)
        if parsed.scheme!='http' or parsed.hostname not in {'127.0.0.1','localhost','::1'} or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            raise ValueError('Cầu nối chỉ kết nối HTTP loopback trên máy chạy web.')
        self.token=(self.data_root/'.ai-company'/'bridge-token').read_text(encoding='utf-8').strip()
        self.http=requests.Session();self.http.trust_env=False
        self.http.headers['Authorization']='Bearer '+self.token
    def post(self,path,data):
        try:response=self.http.post(self.url+'/api/company/worker/'+path,json=data,timeout=10)
        except requests.RequestException:raise RuntimeError('Không kết nối được web điều phối. Kiểm tra backend/port và trạng thái mission.')
        try:body=response.json()
        except ValueError:raise RuntimeError('Web trả lỗi không phải JSON; kiểm tra địa chỉ và backend.')
        if not response.ok or not body.get('ok'):raise RuntimeError(body.get('error') or 'Cầu nối từ chối yêu cầu. Kiểm tra worker và trạng thái mission.')
        return body
    def runtime(self,id):
        if not re.fullmatch(r'[a-f0-9]{32}',id):raise ValueError('Mission ID sai định dạng.')
        data=json.loads((self.root/'.ai-company'/'missions'/id/'runtime.json').read_text(encoding='utf-8'))
        if not isinstance(data.get('lease'),str):raise ValueError('Mission chưa được worker nhận.')
        return data
