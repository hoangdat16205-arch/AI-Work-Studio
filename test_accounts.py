import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from flask import Flask,jsonify
from payos import PayOS
from payos.types import WebhookData
from studio_accounts import register_accounts


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.app=Flask('account-test');self.app.config['TESTING']=True
        @self.app.errorhandler(ValueError)
        def invalid(error):return jsonify(ok=False,error=str(error)),400
        self.store=register_accounts(self.app,self.root,Path(__file__).with_name('AI_Video_Studio_V7_5_Backend_V4Voice.py'),{'SHARED_ELEVENCLIENT':None,'SHARED_ELEVENVOICES':{}})
        self.billing=self.app.extensions['studio_billing']
    def user(self,email='member@example.test',admin=False):
        user=self.store.register(email,'long-enough-password','Test')
        if admin:user=self.store.make_admin(email)
        client=self.app.test_client();csrf=client.get('/api/auth/me').get_json()['csrf']
        data=client.post('/api/auth/login',json={'email':email,'password':'long-enough-password'},headers={'X-CSRF-Token':csrf}).get_json()
        client.environ_base['HTTP_X_CSRF_TOKEN']=data['csrf'];return user,client
    def test_signup_role_password_and_csrf(self):
        client=self.app.test_client();self.assertEqual(client.get('/api/library/records').status_code,401)
        self.assertEqual(client.post('/api/auth/register',json={}).status_code,403)
        csrf=client.get('/api/auth/me').get_json()['csrf']
        data={'email':'new@example.test','password':'a-long-safe-password','name':'New','role':'admin','tier':'pro'}
        response=client.post('/api/auth/register',json=data,headers={'X-CSRF-Token':csrf})
        self.assertEqual(response.status_code,200);user=response.get_json()['user']
        self.assertEqual(user['role'],'member');self.assertEqual(user['tier'],'free');self.assertNotIn('password',user)
        with self.store.connect() as db:password=db.execute('SELECT password FROM users WHERE id=?',(user['id'],)).fetchone()[0]
        self.assertTrue(password.startswith('scrypt:'));self.assertNotEqual(password,data['password'])
        self.assertIn('HttpOnly',response.headers['Set-Cookie']);self.assertIn('SameSite=Lax',response.headers['Set-Cookie'])
        self.assertEqual(client.get('/api/admin/overview').status_code,403)
    def test_two_user_documents_projects_and_files_are_isolated(self):
        first,a=self.user('a@example.test');second,b=self.user('b@example.test')
        saved=a.post('/api/library/records',json={'title':'Private','body':'Only A'}).get_json()['record']
        self.assertEqual(b.get('/api/library/records').get_json()['records'],[])
        self.assertEqual(b.get('/api/library/records/'+saved['id']).status_code,400)
        for client,body in [(a,'A'),(b,'B')]:self.assertEqual(client.post('/api/work/projects',json={'id':'same','project':{'script':body}}).status_code,200)
        self.assertEqual(a.get('/api/work/projects/same').get_json()['project']['script'],'A')
        self.assertEqual(b.get('/api/work/projects/same').get_json()['project']['script'],'B')
        uploaded=a.post('/api/upload',data={'files':(io.BytesIO(b'private-image'),'a.png')}).get_json()['files'][0]
        with a.get(uploaded['url']) as response:self.assertEqual(response.data,b'private-image')
        self.assertEqual(b.get(uploaded['url']).status_code,404)
        (self.store.root(first)/'v7_voice_output'/'same.mp3').write_bytes(b'private-audio')
        with a.get('/audio/same.mp3') as response:self.assertEqual(response.data,b'private-audio')
        self.assertEqual(b.get('/audio/same.mp3').status_code,404)
        id='abcdef0123456789abcdef0123456789';folder=self.store.root(first)/'studio_exports'/id;folder.mkdir();(folder/'output.mp4').write_bytes(b'private-video')
        with a.get('/exports/'+id+'/output.mp4') as response:self.assertEqual(response.data,b'private-video')
        self.assertEqual(b.get('/exports/'+id+'/output.mp4').status_code,404)
    def test_sessions_csrf_logout_and_password_revocation(self):
        user,a=self.user();b=self.app.test_client();csrf=b.get('/api/auth/me').get_json()['csrf']
        result=b.post('/api/auth/login',json={'email':user['email'],'password':'long-enough-password'},headers={'X-CSRF-Token':csrf}).get_json();b.environ_base['HTTP_X_CSRF_TOKEN']=result['csrf']
        self.assertEqual(a.post('/api/support/tickets',json={'subject':'x','body':'x'},headers={'Origin':'https://other.invalid'}).status_code,403)
        result=a.post('/api/auth/password',json={'current':'long-enough-password','password':'new-long-enough-password'}).get_json()
        a.environ_base['HTTP_X_CSRF_TOKEN']=result['csrf'];self.assertIsNone(b.get('/api/auth/me').get_json()['user'])
        self.assertEqual(a.post('/api/auth/logout').status_code,200);self.assertEqual(a.get('/api/library/records').status_code,401)
    def test_free_quota_and_provider_failure_refund(self):
        user,client=self.user();tenant=self.app.extensions['studio_tenants'].get(user);service=tenant.extensions['studio_ai']['service']
        data={'provider':'openai','domain':'education','template':'education-lesson','brief':'A lesson'}
        with patch.object(service,'text',return_value=('Lesson','mock')):
            for _ in range(10):self.assertEqual(client.post('/api/work/generate',json=data).status_code,200)
            self.assertEqual(client.post('/api/work/generate',json=data).status_code,400)
        self.assertEqual(client.post('/api/ai/image',json={'prompt':'An image'}).status_code,402)
        self.assertEqual(client.post('/api/ai/video',json={'scenes':[]}).status_code,402)
        self.assertEqual(client.get('/api/company/bootstrap').status_code,403)
        other,c=self.user('other@example.test');s=self.app.extensions['studio_tenants'].get(other).extensions['studio_ai']['service']
        with patch.object(s,'text',side_effect=ValueError('Missing key')):self.assertEqual(c.post('/api/work/generate',json=data).status_code,400)
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT count FROM usage WHERE user=?',(other['id'],)).fetchone()[0],0)
    def test_manual_pro_only_admin_and_once(self):
        user,client=self.user();admin,owner=self.user('owner@example.test',True)
        with patch.dict('os.environ',{'PRO_PRICE_VND':'199000'}):
            order=client.post('/api/billing/orders',json={'amount':1}).get_json()['order'];self.assertEqual(order['amount'],199000)
        path='/api/admin/orders/'+order['id']+'/review'
        self.assertEqual(client.post(path,json={'decision':'approve'}).status_code,403)
        self.assertEqual(owner.post(path,json={'decision':'approve'}).status_code,400)
        self.assertEqual(owner.post(path,json={'decision':'approve','note':'Matched bank statement','payment_confirmed':True}).status_code,200)
        expiry=self.store.get(user['id'])['pro_until'];self.assertEqual(self.store.get(user['id'])['tier'],'pro')
        self.assertEqual(owner.post(path,json={'decision':'approve','note':'Again','payment_confirmed':True}).status_code,400)
        self.assertEqual(self.store.get(user['id'])['pro_until'],expiry)
        with self.store.connect() as db:db.execute('UPDATE users SET pro_until=? WHERE id=?',(time.time()-1,user['id']))
        self.assertEqual(self.store.get(user['id'])['tier'],'free')
    def test_support_isolation_and_admin_reply(self):
        user,a=self.user();other,b=self.user('b@example.test');admin,owner=self.user('owner@example.test',True)
        id=a.post('/api/support/tickets',json={'subject':'Help','body':'My order'}).get_json()['id']
        self.assertEqual(b.get('/api/support/tickets').get_json()['tickets'],[])
        path='/api/admin/tickets/'+id+'/reply';self.assertEqual(b.post(path,json={'reply':'x'}).status_code,403)
        self.assertEqual(owner.post(path,json={'reply':'Resolved'}).status_code,200)
        self.assertEqual(a.get('/api/support/tickets').get_json()['tickets'][0]['reply'],'Resolved')
        self.assertEqual(a.get('/api/billing/config').get_json()['telegram'],'https://t.me/Grow3833')
    def payment_fixture(self):
        user,client=self.user();sdk=PayOS(client_id='test-client',api_key='test-api',checksum_key='checksum-for-tests')
        self.billing.client=sdk
        self.addCleanup(sdk.close)
        env=patch.dict('os.environ',{'PRO_PRICE_VND':'199000','PUBLIC_BASE_URL':'https://studio.example.test','PAYOS_CLIENT_ID':'test-client','PAYOS_API_KEY':'test-api','PAYOS_CHECKSUM_KEY':'checksum-for-tests'})
        env.start();self.addCleanup(env.stop)
        def create(payment_data):return SimpleNamespace(checkout_url='https://pay.payos.vn/test',amount=payment_data.amount,order_code=payment_data.order_code,payment_link_id='payment-link')
        with patch.object(sdk.payment_requests,'create',side_effect=create):
            response=client.post('/api/billing/payos/checkout',json={'amount':1});self.assertEqual(response.status_code,200);order=response.get_json()['order']
        return user,client,sdk,order
    def signed_payload(self,sdk,order,**changes):
        data=WebhookData(order_code=order['order_code'],amount=order['amount'],description=order['reference'],account_number='123',reference='ref',transaction_date_time='2026-10-04 12:00:00',currency='VND',payment_link_id='payment-link',code='00',desc='success').model_dump_camel_case()
        data.update(changes);signature=sdk.crypto.create_signature_from_object(data,sdk.checksum_key)
        return {'code':'00','desc':'success','success':True,'data':data,'signature':signature}
    def test_payos_signed_webhook_idempotent_and_order_amount(self):
        user,client,sdk,order=self.payment_fixture();self.assertEqual(order['amount'],199000);self.assertEqual(self.store.get(user['id'])['tier'],'free')
        payment=SimpleNamespace(order_code=order['order_code'],amount=199000,amount_paid=199000,status='PAID',id='payment-link')
        payload=self.signed_payload(sdk,order)
        with patch.object(sdk.payment_requests,'get',return_value=payment):
            self.assertEqual(client.post('/api/billing/payos/webhook',json=payload).status_code,200)
            expiry=self.store.get(user['id'])['pro_until'];self.assertEqual(self.store.get(user['id'])['tier'],'pro')
            self.assertEqual(client.post('/api/billing/payos/webhook',json=payload).status_code,200)
            self.assertEqual(client.post('/api/billing/orders/'+order['id']+'/check',json={}).status_code,200)
            self.assertEqual(self.store.get(user['id'])['pro_until'],expiry)
    def test_payos_reject_tamper_wrong_amount_and_other_users(self):
        user,client,sdk,order=self.payment_fixture();payload=self.signed_payload(sdk,order);payload['data']['amount']=1
        with patch.object(sdk.payment_requests,'get') as get:
            self.assertEqual(client.post('/api/billing/payos/webhook',json=payload).status_code,400);get.assert_not_called()
        wrong=SimpleNamespace(order_code=order['order_code'],amount=1,amount_paid=1,status='PAID',id='payment-link')
        with patch.object(sdk.payment_requests,'get',return_value=wrong):self.assertEqual(client.post('/api/billing/payos/webhook',json=self.signed_payload(sdk,order)).status_code,400)
        self.assertEqual(self.store.get(user['id'])['tier'],'free')
        other,b=self.user('other@example.test');self.assertEqual(b.post('/api/billing/orders/'+order['id']+'/check',json={}).status_code,400)
        with patch.object(sdk.payment_requests,'get') as get:
            self.assertEqual(client.post('/api/billing/payos/webhook',json=self.signed_payload(sdk,order,orderCode=123)).status_code,200);get.assert_not_called()
    def test_payos_pending_does_not_upgrade_from_return_query(self):
        user,client,sdk,order=self.payment_fixture();pending=SimpleNamespace(order_code=order['order_code'],amount=199000,amount_paid=0,status='PENDING',id='payment-link')
        with patch.object(sdk.payment_requests,'get',return_value=pending):
            result=client.post('/api/billing/orders/'+order['id']+'/check',json={'status':'PAID'}).get_json();self.assertFalse(result['paid'])
        self.assertEqual(self.store.get(user['id'])['tier'],'free')


if __name__=='__main__':unittest.main()
