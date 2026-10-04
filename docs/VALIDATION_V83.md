# Kiểm chứng V8.3 — 04/10/2026

- 50 test Python qua: provider contract, voice, FFmpeg dựng MP4, nhập/xuất tài liệu, thư viện/phiên bản, tài khoản/quyền/dữ liệu riêng, hạn mức, thanh toán, Kilo và AI riêng.
- PayOS: dùng SDK chính thức để xác minh HMAC thật với fixture; create/get payment dùng mock. Webhook/poll/duyệt thủ công không cộng Pro hai lần.
- Kilo: 24 frontmatter và 2 cấu hình hợp lệ với schema chính thức. Worker được thử qua HTTP và subprocess bằng CLI fixture, gồm kết quả đạt và exit 0 thiếu báo cáo.
- Chromium: đăng ký/đăng nhập, admin/member, nháp và thư viện riêng, import TXT, xuất DOCX thật, bảng 24 vai trò, queue/cancel, duyệt Pro, PayOS checkout fixture, Telegram link, ticket/trả lời, desktop/mobile không tràn ngang hoặc lỗi JavaScript.
- Docker: build thành công, Compose config hợp lệ, Gunicorn khởi động, health/auth/save/export hoạt động. Session/user/thư viện còn sau restart; bridge bị tắt trong môi trường Docker.
- JavaScript: node --check cho bốn module UI qua.

Chưa có credentials OpenAI/Gemini/Claude/Veo/GitHub/PayOS hoặc model GPU/Kilo của chủ website để kiểm tra sinh nội dung, thanh toán và nhiệm vụ AI thật. Không phát sinh gọi API trả phí trong lần kiểm chứng này. Edge TTS từng tạo MP3 thật ở bản trước; chưa benchmark GPU hoặc kiểm thử tải đông khách.
