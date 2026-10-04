"""Official payOS SDK adapter. Redirect parameters never grant Pro."""
import os
import secrets
import ssl
import time
from urllib.parse import urlparse
import httpx
from payos import PayOS
from payos.types import CreatePaymentLinkRequest


def public_origin():
    url=os.getenv('PUBLIC_BASE_URL','').strip().rstrip('/');parsed=urlparse(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:return None
    return url


def payos_ready():return bool(public_origin() and all(os.getenv(k) for k in ['PAYOS_CLIENT_ID','PAYOS_API_KEY','PAYOS_CHECKSUM_KEY']))


class Billing:
    def __init__(self,store):self.store=store;self.client=None
    def sdk(self):
        if not payos_ready():raise ValueError('PayOS chưa cấu hình. Xem hướng dẫn lấy credentials và PUBLIC_BASE_URL.')
        if self.client is None:
            self.client=PayOS(client_id=os.getenv('PAYOS_CLIENT_ID'),api_key=os.getenv('PAYOS_API_KEY'),checksum_key=os.getenv('PAYOS_CHECKSUM_KEY'),timeout=20,max_retries=0,http_client=httpx.Client(verify=ssl.create_default_context()))
        return self.client
    def checkout(self,user):
        client=self.sdk();order=self.store.order(user,'payos');origin=public_origin()
        data=CreatePaymentLinkRequest(order_code=order['order_code'],amount=order['amount'],description=order['reference'],
            return_url=origin+'/?billing=return&order='+order['id'],cancel_url=origin+'/?billing=cancel&order='+order['id'],expired_at=int(time.time())+1800)
        try:response=client.payment_requests.create(payment_data=data)
        except Exception:
            with self.store.connect() as db:db.execute('UPDATE orders SET status="checkout_error" WHERE id=? AND status="pending"',(order['id'],))
            raise ValueError('Chưa xác nhận tạo được checkout PayOS. Kiểm tra cấu hình và đơn hiện có trước khi tạo lại; không tự gửi lại request.')
        parsed=urlparse(response.checkout_url)
        if parsed.scheme!='https' or not parsed.hostname or not (parsed.hostname=='payos.vn' or parsed.hostname.endswith('.payos.vn')):raise ValueError('PayOS trả URL thanh toán không hợp lệ.')
        if response.amount!=order['amount'] or response.order_code!=order['order_code']:raise ValueError('Thông tin checkout không khớp đơn trên server.')
        with self.store.connect() as db:db.execute('UPDATE orders SET checkout_url=?,provider_id=? WHERE id=?',(response.checkout_url,response.payment_link_id,order['id']))
        return self.store.order_by_id(order['id'],user['id'])
    def check(self,user,id):
        order=self.store.order_by_id(id,user['id'])
        if order['method']!='payos':raise ValueError('Đơn này dùng quản trị viên duyệt, không phải PayOS.')
        return self.verify_remote(order)
    def verify_remote(self,order):
        try:payment=self.sdk().payment_requests.get(order['order_code'])
        except Exception:raise ValueError('Chưa xác minh được trạng thái PayOS. Thử kiểm tra lại sau; quyền Pro chưa thay đổi.')
        if payment.order_code!=order['order_code'] or payment.amount!=order['amount']:raise ValueError('Thông tin thanh toán không khớp đơn hàng.')
        if order.get('provider_id') and payment.id!=order['provider_id']:raise ValueError('Payment link không khớp đơn hàng.')
        if payment.status=='PAID' and payment.amount_paid>=order['amount']:
            self.store.apply_paid(order['id']);return {'status':'approved','paid':True}
        return {'status':payment.status,'paid':False}
    def webhook(self,payload):
        try:data=self.sdk().webhooks.verify(payload)
        except Exception:raise ValueError('Webhook PayOS không hợp lệ hoặc sai chữ ký.')
        if data.code!='00' or data.currency!='VND':return {'ignored':True}
        with self.store.connect() as db:row=db.execute('SELECT * FROM orders WHERE order_code=? AND method="payos"',(data.order_code,)).fetchone()
        if not row:return {'ignored':True} # Signed PayOS channel validation sample / unrelated order.
        order=dict(row)
        if order.get('provider_id') and data.payment_link_id!=order['provider_id']:raise ValueError('Webhook không khớp payment link.')
        return self.verify_remote(order)
