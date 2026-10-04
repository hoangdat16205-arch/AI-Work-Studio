# AI Work Studio V8.3

**Một ý tưởng. Cả đội AI cùng làm.**

Flask/Python, giao diện mint tiếng Việt, văn bản/ảnh/voice/video, tài khoản, Pro và công ty AI.

## Tải từ GitHub

**[Tải ZIP V8.3 trực tiếp](https://github.com/hoangdat16205-arch/AI-Work-Studio/archive/refs/tags/v8.3.zip)**. Hoặc mở [Releases V8.3](https://github.com/hoangdat16205-arch/AI-Work-Studio/releases/tag/v8.3) → **Assets** → **Source code (zip)**.

Hoặc bấm **Code** → **Download ZIP**. Giải nén toàn bộ, vào thư mục chứa `start_windows.bat` để chạy.

## Giải nén và chạy Windows

1. Giải nén toàn bộ ZIP vào thư mục, ví dụ `D:\AI_Work_Studio`; đừng chạy trong ZIP.
2. Cài Python 3.11+, bật **Add Python to PATH**. Cài FFmpeg/ffprobe vào PATH để xuất MP4 hoặc dùng Gemini TTS.
3. Mở `start_windows.bat`. Script tạo môi trường, cài thư viện và tạo `.env` từ mẫu nếu chưa có.
4. Mở http://127.0.0.1:5000 → **Đăng ký**. Giữ cửa sổ backend mở.
5. Chủ website mở terminal trong thư mục dự án, cấp admin cho email đã đăng ký:

```bat
.venv\Scripts\python.exe tools\manage_accounts.py --make-admin email-cua-ban@example.com
```

6. Tải lại web để có **Quản trị** và **Công ty AI**. Khách hàng có dữ liệu riêng.
7. Điền API cần dùng trong `.env`, restart backend.

macOS/Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python AI_Video_Studio_V7_5_Backend_V4Voice.py
```

Chỉ copy mẫu khi chưa có `.env`; giữ key và dữ liệu khi cập nhật.

## Chức năng

- Văn bản: 32 mẫu/8 lĩnh vực, nhập PDF có text/DOCX/TXT/MD, sửa/xem trước, xuất Word/TXT/Markdown, in PDF qua trình duyệt.
- Thư viện tìm kiếm, phiên bản, dự án local; dữ liệu tách theo tài khoản.
- OpenAI/Gemini/Claude/**AI riêng**: văn bản, kịch bản, dịch, chia cảnh.
- Ảnh OpenAI/Gemini; Google Veo chính thức và lưu operation để tiếp tục theo dõi.
- Voice: cache 322 giọng Edge, ElevenLabs theo tài khoản, 13 OpenAI/30 Gemini khi có key; test/nghe/sửa/tạo lại từng đoạn, phát nối tiếp, MP3/ZIP.
- Media, nhạc upload, chỉnh SRT, xuất MP4 bằng FFmpeg; 16:9/9:16/1:1, 720p/1080p.
- GitHub snapshot, kiểm tra revision, commit nguyên tử; ghi repo dành cho admin.
- 24 vai trò Kilo, quản lý + 23 nhân viên; task/phụ thuộc/bằng chứng, cấu hình và bridge CLI.
- Đăng ký/đăng nhập/đổi mật khẩu, phân quyền, Free/Pro, PayOS, admin duyệt Pro, ticket + https://t.me/Grow3833.
- Docker và thư mục dữ liệu độc lập để chuyển máy chủ.

## Hướng dẫn

| Mục tiêu | Tài liệu |
|---|---|
| Cài Kilo/24 vai trò | [docs/AI_COMPANY_VI.md](docs/AI_COMPANY_VI.md) |
| Tài khoản/Pro/PayOS/CSKH | [docs/ACCOUNTS_PRO_VI.md](docs/ACCOUNTS_PRO_VI.md) |
| AI riêng/GPU/Docker/nâng cấp | [docs/ARCHITECTURE_VI.md](docs/ARCHITECTURE_VI.md) |
| Key/endpoint chính thức | [docs/API_SETUP_VI.md](docs/API_SETUP_VI.md) |
| Công việc đa lĩnh vực | [docs/WORKSPACE_VI.md](docs/WORKSPACE_VI.md) |

**Pro chưa mở bán:** `PRO_PRICE_VND=0` vì chưa chốt giá. PayOS cần credentials thật/domain HTTPS. Telegram `@Grow3833` là nút liên hệ; chưa có bot gửi thông báo.

## Triển khai và giới hạn

Code/dữ liệu tách bằng `STUDIO_DATA_ROOT`. AI riêng có adapter văn bản/chia cảnh và endpoint/model/key; GPU inference chạy riêng. Ảnh/TTS/video riêng cần adapter tương ứng.

Docker dùng **1 web worker/4 thread**. Chưa có Postgres/Redis/hàng đợi phân tán; không tăng worker/replica trước khi tách registry khỏi bộ nhớ. Kilo bridge chỉ cho admin localhost, bị tắt trong Compose.

Chưa có xác minh email, khôi phục mật khẩu qua email, 2FA, workspace doanh nghiệp chung, hóa đơn thuế, OCR, PPTX, Hyperframes hoặc Sora. Mẫu chuyên ngành cần đối chiếu nguồn.

## Kiểm chứng

```sh
python -m unittest discover -p "test_*.py"
```

Test gồm FFmpeg thật, import/export, phiên bản, dữ liệu riêng, CSRF/quyền, hạn mức, Pro idempotent, SDK PayOS/chữ ký, 24 vai trò và worker HTTP/subprocess.

API trả phí, AI riêng và Kilo thực thi AI dùng fixture; chưa có credentials/model GPU của chủ website. Worker thử với CLI giả lập giao thức, agent đối chiếu schema chính thức. Edge TTS đã tạo MP3 thật trong lần kiểm tra trước.

Ảnh `preview-company-*.png` là minh họa. Tài khoản/token/database/tệp khách/`.env` thật không nằm trong ZIP.
