# Tài khoản, Pro và CSKH

## Tài khoản/admin

Đăng ký tên/email/mật khẩu 12–128 ký tự. User mới là Free. Mật khẩu scrypt, cookie HttpOnly/SameSite, CSRF. Không admin/mật khẩu mặc định.

Cấp admin cho email đã đăng ký từ terminal chủ máy:

```sh
python tools/manage_accounts.py --make-admin email-cua-ban@example.com
```

Windows dùng `.venv\Scripts\python.exe`; Docker `docker compose exec web python ...`. Helper đọc `.env`/data-root. Tải lại web.

User không đọc được thư viện/voice/media/đơn/ticket của user khác. Admin quản lý đơn/ticket; chưa có giao diện đọc toàn bộ nội dung riêng khách. GitHub ghi repo/Công ty AI dành cho admin.

Đổi mật khẩu làm session cũ hết hiệu lực. Chưa có xác minh email, social login, khôi phục qua email hoặc 2FA.

## Giá/hạn mức

Pro **30 ngày**, gia hạn nối tiếp nếu còn hạn. Chưa chốt giá:

```env
PRO_PRICE_VND=0
```

0 khóa mở đơn. Đổi sang giá VND nguyên dương khi chốt giá/chi phí. Giá trong ảnh/test là minh họa. Server quyết định giá, không nhận từ trình duyệt.

Hạn mức/ngày UTC:

| Quyền | Free | Pro |
|---|---:|---:|
| Văn bản/chia cảnh | 10 | 200 |
| Tạo ảnh | 0 | 50 |
| Tạo/resume batch Veo | 0 | 3 |
| Giọng API OpenAI/Gemini/ElevenLabs | Không | Có |
| Edge, nhập/sửa/lưu/xuất tài liệu | Có | Có |

Không cam kết chi phí tối đa: batch có nhiều clip, voice/độ dài có chi phí riêng. Admin bỏ qua hạn mức. Chỉnh `billing_config()` trong `studio_accounts.py`; lỗi API hoàn lượt.

## PayOS

SDK chính thức `payos` 1.x; https://payos.vn/docs/api/.

1. Đăng ký PayOS, kết nối tài khoản nhận tiền, tạo kênh theo dashboard.
2. Lấy **Client ID/API Key/Checksum Key**.
3. Domain HTTPS nhận webhook, cấu hình backend:

```env
PRO_PRICE_VND=GIA-VND-BAN-CHOT
PAYOS_CLIENT_ID=CLIENT-ID-CUA-KENH
PAYOS_API_KEY=API-KEY-CUA-KENH
PAYOS_CHECKSUM_KEY=CHECKSUM-KEY-CUA-KENH
PUBLIC_BASE_URL=https://domain-cua-ban
COOKIE_SECURE=true
```

Trên là chỗ điền. Origin không path/query. Restart.

4. Đăng ký/xác nhận webhook trên dashboard:

```text
https://domain-cua-ban/api/billing/payos/webhook
```

Mẫu xác nhận có chữ ký được chấp nhận, không cấp Pro nếu mã đơn không thuộc hệ thống.

5. Tài khoản thử → Gói dịch vụ → PayOS. Đối chiếu mã đơn/giá/người nhận trước thanh toán.
6. Webhook xác minh chữ ký, backend đọc PayOS/so mã đơn/số tiền/payment link. Chỉ `PAID` đủ tiền cấp Pro. Nút kiểm tra cùng quy trình.
7. Kiểm tra lịch sử/thời hạn; webhook hoặc kiểm tra lặp không gia hạn hai lần.

URL `billing=return`/`status=PAID` không cấp Pro. Localhost chưa nhận webhook đầy đủ. Checkout timeout cần kiểm tra đơn/dashboard trước khi tạo lại; không tự retry.

Chưa recurring/tự hoàn tiền/hủy link UI/hóa đơn thuế. Chưa giao dịch PayOS thật; cần thử giao dịch nhỏ bằng domain/credentials của bạn trước mở bán.

## Duyệt thủ công

```env
PRO_BANK_NAME=TEN-NGAN-HANG
PRO_BANK_ACCOUNT=SO-TAI-KHOAN
PRO_BANK_HOLDER=TEN-CHU-TAI-KHOAN
```

Khách tạo đơn/chuyển mã tham chiếu. Chủ website đối chiếu tiền thực nhận → Quản trị → Duyệt, xác nhận đã đối chiếu và ghi chú; có thể từ chối.

Chỉ admin duyệt; bấm lại không cộng hạn. Không dựa riêng ảnh biên lai. Đơn PayOS đã duyệt thủ công không cấp lần nữa khi webhook về sau.

## CSKH/dữ liệu

`TELEGRAM_SUPPORT_USERNAME=Grow3833` mở https://t.me/Grow3833. Chưa bot tự đọc/gửi Telegram.

Hỗ trợ tạo ticket, user thấy của mình. Admin trả lời tại Quản trị. Không yêu cầu mật khẩu/key trong ticket.

Sao lưu toàn bộ data-root gồm user/đơn/ticket/hạn mức/audit/session secret. Cập nhật giữ `.env`, `.accounts`, `runtime`.
