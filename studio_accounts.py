"""Accounts, local-admin billing review, sessions and isolated studio tenants."""
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import types
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from uuid import uuid4
from flask import g,jsonify,request,session,Response
from werkzeug.security import generate_password_hash,check_password_hash


class Accounts:
    def __init__(self,base):
        self.base=Path(base).resolve();self.directory=self.base/'.accounts';self.directory.mkdir(exist_ok=True)
        self.path=self.directory/'accounts.sqlite3';secret_path=self.directory/'session-secret'
        try:
            with secret_path.open('x',encoding='utf-8') as f:f.write(secrets.token_urlsafe(48))
            secret_path.chmod(0o600)
        except FileExistsError:pass
        self.secret=os.getenv('APP_SECRET_KEY') or secret_path.read_text().strip()
        self.dummy_hash=generate_password_hash(secrets.token_urlsafe(32))
        with self.connect() as db:db.executescript('''
            CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE,name TEXT,password TEXT,role TEXT,pro_until REAL,created REAL);
            CREATE TABLE IF NOT EXISTS attempts(bucket TEXT,created REAL);
            CREATE TABLE IF NOT EXISTS usage(user TEXT,day TEXT,feature TEXT,count INTEGER,PRIMARY KEY(user,day,feature));
            CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,user TEXT,status TEXT,amount INTEGER,days INTEGER,reference TEXT,created REAL,reviewed REAL,reviewer TEXT,note TEXT);
            CREATE TABLE IF NOT EXISTS tickets(id TEXT PRIMARY KEY,user TEXT,subject TEXT,body TEXT,status TEXT,reply TEXT,created REAL,updated REAL);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,actor TEXT,action TEXT,target TEXT,created REAL);
        ''')
        with self.connect() as db:
            user_columns={row['name'] for row in db.execute('PRAGMA table_info(users)')}
            if 'auth_version' not in user_columns:db.execute('ALTER TABLE users ADD COLUMN auth_version INTEGER DEFAULT 1')
            columns={row['name'] for row in db.execute('PRAGMA table_info(orders)')}
            for name,definition in {'method':'TEXT DEFAULT "manual"','order_code':'INTEGER','checkout_url':'TEXT DEFAULT ""','provider_id':'TEXT DEFAULT ""'}.items():
                if name not in columns:db.execute(f'ALTER TABLE orders ADD COLUMN {name} {definition}')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS order_code_unique ON orders(order_code)')
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=15);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()
    def rate(self,bucket,limit=10,seconds=300):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');db.execute('DELETE FROM attempts WHERE created<?',(time.time()-3600,))
            count=db.execute('SELECT COUNT(*) FROM attempts WHERE bucket=? AND created>?',(bucket,time.time()-seconds)).fetchone()[0]
            if count>=limit:raise ValueError('Thao tác quá nhanh. Chờ vài phút rồi thử lại.')
            db.execute('INSERT INTO attempts VALUES(?,?)',(bucket,time.time()))
    @staticmethod
    def email(value):
        if not isinstance(value,str) or len(value)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',value.strip()):raise ValueError('Nhập địa chỉ email hợp lệ.')
        return value.strip().lower()
    @staticmethod
    def password(value):
        if not isinstance(value,str) or not 12<=len(value)<=128:raise ValueError('Mật khẩu cần 12–128 ký tự.')
        return value
    def register(self,email,password,name):
        email=self.email(email);password=self.password(password)
        if not isinstance(name,str) or not 1<=len(name.strip())<=100:raise ValueError('Tên hiển thị cần 1–100 ký tự.')
        id=uuid4().hex
        try:
            with self.connect() as db:db.execute('INSERT INTO users(id,email,name,password,role,pro_until,created) VALUES(?,?,?,?,?,?,?)',(id,email,name.strip(),generate_password_hash(password),'member',0,time.time()))
        except sqlite3.IntegrityError:raise ValueError('Không tạo được tài khoản với email này. Thử đăng nhập hoặc liên hệ hỗ trợ.')
        return self.get(id)
    def authenticate(self,email,password):
        email=self.email(email)
        if not isinstance(password,str) or len(password)>128:raise ValueError('Email hoặc mật khẩu không đúng.')
        with self.connect() as db:row=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
        valid=check_password_hash(row['password'] if row else self.dummy_hash,password)
        if not row or not valid:raise ValueError('Email hoặc mật khẩu không đúng.')
        return self.public(dict(row))
    @staticmethod
    def public(row):
        return {k:row[k] for k in ['id','email','name','role','pro_until','created','auth_version']}|{'tier':'pro' if row['role']=='admin' or row['pro_until']>time.time() else 'free'}
    def get(self,id):
        with self.connect() as db:row=db.execute('SELECT * FROM users WHERE id=?',(id,)).fetchone()
        return self.public(dict(row)) if row else None
    def make_admin(self,email):
        with self.connect() as db:
            row=db.execute('SELECT id FROM users WHERE email=?',(self.email(email),)).fetchone()
            if not row:raise ValueError('Email chưa đăng ký. Đăng ký trên web trước.')
            db.execute('UPDATE users SET role="admin" WHERE id=?',(row['id'],))
            db.execute('INSERT INTO audit(actor,action,target,created) VALUES(?,?,?,?)',('local-owner','make_admin',row['id'],time.time()))
        return self.get(row['id'])
    def root(self,user):
        if not re.fullmatch(r'[a-f0-9]{32}',user['id']):raise ValueError('ID người dùng không hợp lệ.')
        root=self.directory/'data'/user['id'];root.mkdir(parents=True,exist_ok=True);return root
    def change_password(self,id,current,new):
        new=self.password(new)
        with self.connect() as db:
            row=db.execute('SELECT password FROM users WHERE id=?',(id,)).fetchone()
            if not isinstance(current,str) or not row or not check_password_hash(row['password'],current):raise ValueError('Mật khẩu hiện tại không đúng.')
            db.execute('UPDATE users SET password=?,auth_version=auth_version+1 WHERE id=?',(generate_password_hash(new),id))
    def consume(self,user,feature,limit):
        day=time.strftime('%Y-%m-%d',time.gmtime())
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT count FROM usage WHERE user=? AND day=? AND feature=?',(user['id'],day,feature)).fetchone()
            if row and row['count']>=limit:raise ValueError('Đã đạt giới hạn sử dụng hôm nay. Xem trang gói Pro hoặc thử lại ngày mai.')
            db.execute('INSERT INTO usage VALUES(?,?,?,1) ON CONFLICT(user,day,feature) DO UPDATE SET count=count+1',(user['id'],day,feature))
        return day
    def refund(self,user,day,feature):
        with self.connect() as db:db.execute('UPDATE usage SET count=MAX(0,count-1) WHERE user=? AND day=? AND feature=?',(user,day,feature))
    def order(self,user,method='manual'):
        amount=pro_price()
        if not amount:raise ValueError('Gói Pro chưa mở bán. Chủ website cần cấu hình giá và thông tin thanh toán.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM orders WHERE user=? AND status="pending"',(user['id'],)).fetchone():raise ValueError('Bạn đã có yêu cầu Pro đang chờ duyệt.')
            id=uuid4().hex;reference='PRO'+id[:10].upper()
            order_code=secrets.randbelow(9_000_000_000_000)+1_000_000_000_000
            db.execute('INSERT INTO orders(id,user,status,amount,days,reference,created,reviewed,reviewer,note,method,order_code) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(id,user['id'],'pending',amount,30,reference,time.time(),None,None,'',method,order_code))
        return self.orders(user['id'])[0]
    def order_by_id(self,id,user):
        with self.connect() as db:row=db.execute('SELECT * FROM orders WHERE id=? AND user=?',(id,user)).fetchone()
        if not row:raise ValueError('Không tìm thấy đơn hàng của tài khoản này.')
        return dict(row)
    def apply_paid(self,id):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM orders WHERE id=? AND method="payos"',(id,)).fetchone()
            if not row:raise ValueError('Đơn PayOS không tồn tại.')
            if row['status']=='approved':return # Idempotent even if webhook and polling race.
            if row['status'] not in {'pending','checkout_error'}:raise ValueError('Đơn đã bị từ chối. Quản trị viên cần đối chiếu giao dịch.')
            current=db.execute('SELECT pro_until FROM users WHERE id=?',(row['user'],)).fetchone()[0]
            db.execute('UPDATE users SET pro_until=? WHERE id=?',(max(time.time(),current)+row['days']*86400,row['user']))
            db.execute('UPDATE orders SET status="approved",reviewed=?,reviewer="payos",note="Server verified PAID" WHERE id=?',(time.time(),id))
            db.execute('INSERT INTO audit(actor,action,target,created) VALUES(?,?,?,?)',('payos','pro_paid',id,time.time()))
    def orders(self,user=None):
        with self.connect() as db:return [dict(r) for r in db.execute('SELECT o.*,u.email,u.name FROM orders o JOIN users u ON u.id=o.user WHERE (? IS NULL OR o.user=?) ORDER BY o.created DESC LIMIT 100',(user,user))]
    def review_order(self,admin,id,decision,note):
        if decision not in {'approve','reject'} or not isinstance(note,str) or len(note)>1000:raise ValueError('Quyết định duyệt không hợp lệ.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM orders WHERE id=?',(id,)).fetchone()
            if not row or row['status']!='pending':raise ValueError('Yêu cầu đã được xử lý hoặc không tồn tại.')
            if decision=='approve':
                current=db.execute('SELECT pro_until FROM users WHERE id=?',(row['user'],)).fetchone()[0]
                db.execute('UPDATE users SET pro_until=? WHERE id=?',(max(time.time(),current)+row['days']*86400,row['user']))
            db.execute('UPDATE orders SET status=?,reviewed=?,reviewer=?,note=? WHERE id=?',('approved' if decision=='approve' else 'rejected',time.time(),admin['id'],note,id))
            db.execute('INSERT INTO audit(actor,action,target,created) VALUES(?,?,?,?)',(admin['id'],'pro_'+decision,id,time.time()))
    def ticket(self,user,subject,body):
        if not isinstance(subject,str) or not 1<=len(subject.strip())<=160 or not isinstance(body,str) or not 1<=len(body.strip())<=5000:raise ValueError('Nhập tiêu đề và nội dung hỗ trợ hợp lệ.')
        id=uuid4().hex
        with self.connect() as db:db.execute('INSERT INTO tickets VALUES(?,?,?,?,?,?,?,?)',(id,user['id'],subject.strip(),body.strip(),'open','',time.time(),time.time()))
        return id
    def tickets(self,user=None):
        with self.connect() as db:return [dict(r) for r in db.execute('SELECT t.*,u.email,u.name FROM tickets t JOIN users u ON u.id=t.user WHERE (? IS NULL OR t.user=?) ORDER BY t.updated DESC LIMIT 100',(user,user))]
    def reply(self,admin,id,message):
        if not isinstance(message,str) or not 1<=len(message.strip())<=5000:raise ValueError('Phản hồi cần 1–5000 ký tự.')
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM tickets WHERE id=?',(id,)).fetchone():raise ValueError('Không tìm thấy yêu cầu hỗ trợ.')
            db.execute('UPDATE tickets SET reply=?,status="answered",updated=? WHERE id=?',(message.strip(),time.time(),id))
            db.execute('INSERT INTO audit(actor,action,target,created) VALUES(?,?,?,?)',(admin['id'],'support_reply',id,time.time()))


def pro_price():
    try:value=int(os.getenv('PRO_PRICE_VND','0'))
    except ValueError:return 0
    return value if 10000<=value<=100000000 else 0


def billing_config():
    from studio_billing import payos_ready
    name=os.getenv('TELEGRAM_SUPPORT_USERNAME','Grow3833').lstrip('@').strip()
    telegram='https://t.me/'+name if re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]{4,31}',name) else None
    return dict(price=pro_price(),currency='VND',days=30,payment_mode='payos_and_manual',payos_configured=payos_ready(),telegram=telegram,
                bank_name=os.getenv('PRO_BANK_NAME',''),bank_account=os.getenv('PRO_BANK_ACCOUNT',''),bank_holder=os.getenv('PRO_BANK_HOLDER',''),
                open=bool(pro_price()),
                limits={'free':{'text':10,'image':0,'video':0},'pro':{'text':200,'image':50,'video':3}})


class TenantStudios:
    """Independent Flask apps keep every existing media/job closure user-local."""
    def __init__(self,accounts,source,shared):self.accounts=accounts;self.source=Path(source);self.shared=shared;self.lock=threading.Lock();self.apps={}
    def get(self,user):
        with self.lock:
            if user['id'] not in self.apps:
                module=types.ModuleType('tenant_studio_'+user['id'])
                module.__file__=str(self.source)
                module.__dict__.update(IS_TENANT=True,TENANT_BASE_DIR=self.accounts.root(user),**self.shared)
                exec(compile(self.source.read_text(encoding='utf-8'),str(self.source),'exec'),module.__dict__)
                self.apps[user['id']]=module.app
            return self.apps[user['id']]


def register_accounts(app,base,source,shared):
    store=Accounts(base);app.extensions['studio_auth']=store;tenants=TenantStudios(store,source,shared);app.extensions['studio_tenants']=tenants
    from studio_billing import Billing
    billing=Billing(store);app.extensions['studio_billing']=billing
    app.secret_key=store.secret;app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE','false').lower()=='true',PERMANENT_SESSION_LIFETIME=timedelta(hours=8))
    def csrf():
        if 'csrf' not in session:session['csrf']=secrets.token_urlsafe(32)
        return session['csrf']
    def body():
        data=request.get_json()
        if not isinstance(data,dict):raise ValueError('Dữ liệu phải là JSON object.')
        return data
    @app.before_request
    def authenticate_and_isolate():
        # Isolated legacy unit fixtures can exercise the original handlers.
        # There is no environment variable or request that enables this.
        if app.config.get('TESTING') and app.config.get('AUTH_TEST_BYPASS'):return
        if request.path.startswith(('/api/auth/','/api/billing/','/api/support/','/api/admin/')):request.max_content_length=65536
        g.user=store.get(session.get('user_id')) if session.get('user_id') else None
        if g.user and session.get('auth_version')!=g.user['auth_version']:session.clear();g.user=None
        if not (request.path.startswith('/api/') or request.path.startswith(('/assets/','/audio/','/exports/'))):return
        worker=request.path.startswith('/api/company/worker/')
        if worker:return # CompanyStore requires loopback + bearer token + active lease.
        if request.path=='/api/billing/payos/webhook':return # SDK signature verification and server-side payment lookup.
        if request.path not in {'/api/auth/me','/api/auth/login','/api/auth/register','/api/billing/config'} and not g.user:
            return jsonify(ok=False,error='Đăng nhập để sử dụng không gian làm việc.'),401
        if request.method in {'POST','PUT','PATCH','DELETE'}:
            origin=request.headers.get('Origin')
            from urllib.parse import urlparse
            if (origin and urlparse(origin).netloc!=request.host) or not hmac.compare_digest(request.headers.get('X-CSRF-Token',''),csrf()):
                return jsonify(ok=False,error='Phiên thao tác không hợp lệ. Tải lại trang rồi thử lại.'),403
        if request.path.startswith(('/api/admin/','/api/company/','/api/github/')) or request.path in {'/api/voices/refresh','/api/edge-voices/refresh'}:
            if not g.user or g.user['role']!='admin':return jsonify(ok=False,error='Chức năng này dành cho quản trị viên.'),403
        if g.user and request.method=='POST':
            path=request.path;data=request.get_json(silent=True) or {};feature=None
            if path in {'/api/work/generate','/api/ai/text','/api/ai/scenes'}:feature='text'
            elif path=='/api/ai/image':feature='image'
            elif path=='/api/ai/video' or re.fullmatch(r'/api/ai/video/[^/]+/resume',path):feature='video'
            elif path in {'/api/voice','/api/test-voice'} and isinstance(data,dict):
                voice=str(data.get('voice','Tự động'));premium=voice.startswith(('OpenAI -','Gemini -','ElevenLabs -')) or (voice=='Tự động' and bool(os.getenv('ELEVENLABS_API_KEY')))
                if premium and g.user['tier']!='pro':return jsonify(ok=False,error='Giọng API cao cấp cần gói Pro. Bạn có thể dùng giọng Edge ở gói Free.'),402
            if feature:
                limit=billing_config()['limits'][g.user['tier']][feature]
                if not limit:return jsonify(ok=False,error='Tính năng này thuộc gói Pro. Mở trang Gói dịch vụ để xem quyền sử dụng.'),402
                if g.user['role']!='admin':g.usage=(g.user['id'],store.consume(g.user,feature,limit),feature)
        if not request.path.startswith(('/api/auth/','/api/billing/','/api/admin/','/api/support/','/api/company/')) and g.user:
            tenant=tenants.get(g.user)
            environ=request.environ.copy()
            if request.mimetype=='application/json':
                payload=request.get_data();environ['wsgi.input']=io.BytesIO(payload);environ['CONTENT_LENGTH']=str(len(payload))
            return Response.from_app(tenant.wsgi_app,environ)
    @app.after_request
    def response_headers(response):
        response.headers['X-Content-Type-Options']='nosniff';response.headers['Referrer-Policy']='same-origin';response.headers['X-Frame-Options']='SAMEORIGIN'
        if request.path.startswith('/api/'):response.headers['Cache-Control']='no-store'
        if response.status_code>=400 and getattr(g,'usage',None):store.refund(*g.usage)
        return response
    @app.get('/api/auth/me')
    def me():return jsonify(ok=True,user=g.user,csrf=csrf(),billing=billing_config())
    @app.post('/api/auth/register')
    def register():
        store.rate('register:'+str(request.remote_addr),5,600);data=body();user=store.register(data.get('email'),data.get('password'),data.get('name'))
        session.clear();session['user_id']=user['id'];session['auth_version']=user['auth_version'];session.permanent=True
        return jsonify(ok=True,user=user,csrf=csrf())
    @app.post('/api/auth/login')
    def login():
        store.rate('login:'+str(request.remote_addr));data=body();user=store.authenticate(data.get('email'),data.get('password'))
        session.clear();session['user_id']=user['id'];session['auth_version']=user['auth_version'];session.permanent=True
        return jsonify(ok=True,user=user,csrf=csrf())
    @app.post('/api/auth/logout')
    def logout():session.clear();return jsonify(ok=True,csrf=csrf())
    @app.post('/api/auth/password')
    def password():
        data=body();store.change_password(g.user['id'],data.get('current'),data.get('password'));session['auth_version']=store.get(g.user['id'])['auth_version'];session['csrf']=secrets.token_urlsafe(32);return jsonify(ok=True,csrf=csrf())
    @app.get('/api/billing/config')
    def config():return jsonify(ok=True,**billing_config())
    @app.get('/api/billing/orders')
    def orders():return jsonify(ok=True,orders=store.orders(g.user['id']))
    @app.post('/api/billing/orders')
    def create_order():
        if not billing_config()['open']:raise ValueError('Gói Pro chưa mở bán. Chủ website cần cấu hình thông tin thanh toán.')
        store.rate('order:'+g.user['id'],5,600);return jsonify(ok=True,order=store.order(g.user))
    @app.post('/api/billing/payos/checkout')
    def payos_checkout():
        store.rate('checkout:'+g.user['id'],5,600);return jsonify(ok=True,order=billing.checkout(g.user))
    @app.post('/api/billing/orders/<id>/check')
    def payos_check(id):
        store.rate('check:'+g.user['id'],20,60);return jsonify(ok=True,**billing.check(g.user,id))
    @app.post('/api/billing/payos/webhook')
    def payos_webhook():
        if request.content_length and request.content_length>65536:return jsonify(ok=False,error='Webhook quá lớn.'),413
        return jsonify(ok=True,**billing.webhook(request.get_data()))
    @app.get('/api/support/tickets')
    def tickets():return jsonify(ok=True,tickets=store.tickets(g.user['id']))
    @app.post('/api/support/tickets')
    def create_ticket():
        store.rate('ticket:'+g.user['id'],5,600);data=body();return jsonify(ok=True,id=store.ticket(g.user,data.get('subject'),data.get('body')))
    @app.get('/api/admin/overview')
    def admin_overview():return jsonify(ok=True,orders=store.orders(),tickets=store.tickets())
    @app.post('/api/admin/orders/<id>/review')
    def admin_review(id):
        data=body()
        if data.get('decision')=='approve' and (data.get('payment_confirmed') is not True or not str(data.get('note','')).strip()):raise ValueError('Xác nhận đã đối chiếu thanh toán và ghi chú trước khi duyệt Pro.')
        store.review_order(g.user,id,data.get('decision'),data.get('note',''));return jsonify(ok=True)
    @app.post('/api/admin/tickets/<id>/reply')
    def admin_reply(id):store.reply(g.user,id,body().get('reply'));return jsonify(ok=True)
    return store
