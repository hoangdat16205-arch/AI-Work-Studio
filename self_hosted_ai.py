"""Replaceable text adapter for an operator-configured OpenAI-compatible server.

The UI never supplies base URLs or credentials. Images, speech and video need
their own documented adapters; Chat Completions does not imply those APIs.
"""
import os
import re
from urllib.parse import urlparse


class SelfHostedText:
    def __init__(self,http):self.http=http
    def status(self):
        return {'id':'self_hosted','label':'AI riêng / máy chủ GPU','configured':bool(os.getenv('SELF_HOSTED_BASE_URL') and os.getenv('SELF_HOSTED_MODEL')),
                'model':os.getenv('SELF_HOSTED_MODEL','Chưa chọn model'),'capabilities':['text','scenes'],'key_variable':'SELF_HOSTED_BASE_URL / SELF_HOSTED_MODEL'}
    def settings(self,model=None):
        from ai_providers import ProviderError
        base=os.getenv('SELF_HOSTED_BASE_URL','').strip().rstrip('/');parsed=urlparse(base)
        if not base:raise ProviderError('Chưa cấu hình SELF_HOSTED_BASE_URL và SELF_HOSTED_MODEL.',400)
        if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:raise ValueError('Base URL của AI riêng không hợp lệ. Cấu hình trên server, không đặt credentials trong URL.')
        model=model or os.getenv('SELF_HOSTED_MODEL','')
        if not isinstance(model,str) or not re.fullmatch(r'[a-zA-Z0-9._:/-]{1,150}',model):raise ValueError('Nhập ID model thực tế của máy chủ AI riêng.')
        headers={'Content-Type':'application/json'};key=os.getenv('SELF_HOSTED_API_KEY','').strip()
        if key:headers['Authorization']='Bearer '+key
        return base,model,headers
    def check(self):
        from ai_providers import ProviderError
        base,model,headers=self.settings();response=self.http.json('GET',base+'/models',headers=headers)
        if not isinstance(response,dict):raise ProviderError('AI riêng chưa trả danh mục /models hợp lệ.')
        if model not in {item.get('id') for item in response.get('data',[]) if isinstance(item,dict)}:raise ProviderError('Máy chủ AI riêng chưa công bố model được cấu hình. Kiểm tra /models và ID model.',400)
        return {'message':'Đã đọc danh mục model của máy chủ AI riêng. Khả năng sinh nội dung cần kiểm tra bằng yêu cầu thực tế.'}
    def text(self,prompt,system,model=None):
        from ai_providers import ProviderError
        base,model,headers=self.settings(model)
        try:budget=int(os.getenv('SELF_HOSTED_MAX_TOKENS') or '8000')
        except ValueError:raise ValueError('SELF_HOSTED_MAX_TOKENS phải là số nguyên từ 1 đến 32768.') from None
        if not 1<=budget<=32768:raise ValueError('SELF_HOSTED_MAX_TOKENS phải từ 1 đến 32768, phù hợp giới hạn model.')
        response=self.http.json('POST',base+'/chat/completions',headers=headers,json={'model':model,'messages':[{'role':'system','content':system},{'role':'user','content':prompt}],'max_tokens':budget,'stream':False})
        try:content=response['choices'][0]['message']['content']
        except (KeyError,IndexError,TypeError):raise ProviderError('AI riêng chưa trả response Chat Completions hợp lệ.')
        if isinstance(content,list):content='\n'.join(str(c.get('text','')) for c in content if isinstance(c,dict) and c.get('type')=='text')
        if not isinstance(content,str) or not content.strip():raise ProviderError('AI riêng trả nội dung rỗng.')
        if len(content)>50000:raise ProviderError('Kết quả AI riêng vượt 50.000 ký tự. Giảm độ dài yêu cầu.')
        return content.strip(),model
