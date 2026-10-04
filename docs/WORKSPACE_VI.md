# AI Work Studio V8.3 — hướng dẫn dùng cho nhiều công việc

## Bắt đầu

1. Cài Python 3.11+; cài FFmpeg nếu muốn dùng Gemini TTS hoặc xuất video.
2. Giải nén và chạy `start_windows.bat`. Script tự cài/cập nhật thư viện.
3. Mở http://127.0.0.1:5000.
4. Đăng ký/đăng nhập; chọn Văn bản, Hình ảnh, Video Studio hoặc lĩnh vực trên Tổng quan.
5. Để tạo bằng AI, điền key trong `.env` và restart backend. Cách lấy key: [API_SETUP_VI.md](API_SETUP_VI.md).

Không cần API key để nhập/chỉnh tài liệu, xuất Word/TXT/Markdown, in/lưu PDF, dùng thư viện và lưu dự án trên máy. Voice Edge và xuất FFmpeg cần các điều kiện tương ứng ở hướng dẫn bản trước.

## 32 mẫu công việc

| Lĩnh vực | Mẫu có sẵn |
|---|---|
| Giáo dục | Giáo án, câu hỏi ôn tập, tiêu chí đánh giá, bài học dễ hiểu |
| Chính trị & chính sách | Bản tin chính sách, so sánh phương án, kiến thức công dân, thông tin công chúng |
| Y tế & sức khỏe | Tài liệu sức khỏe, tóm tắt tài liệu y tế, hỏi đáp sức khỏe, nội dung poster |
| Marketing | Kế hoạch chiến dịch, bài đăng mạng xã hội, mô tả sản phẩm, chuỗi email |
| Doanh nghiệp | Đề xuất, biên bản họp, SOP, email công việc |
| Nghiên cứu | Tóm tắt tài liệu, tổng quan nguồn, kế hoạch nghiên cứu, diễn giải dữ liệu |
| Sáng tạo nội dung | Bài viết, câu chuyện, kịch bản đa phương tiện, ý tưởng hình ảnh |
| Công việc hằng ngày | Tóm tắt, dịch, dàn ý/kế hoạch, yêu cầu tự do |

Các mẫu là cấu trúc bản thảo và hướng dẫn AI, không phải dữ liệu chuyên ngành đã kiểm chứng hoặc công cụ chẩn đoán. Nhập tài liệu nguồn để AI có cơ sở. Văn bản y tế hướng tới giáo dục/biên tập; chính sách hướng tới thông tin và phân tích có nguồn. Nội dung cần độ chính xác cao nên được đối chiếu với nguồn và người có chuyên môn trước khi sử dụng.

## Văn bản

- Chọn lĩnh vực và mẫu, nhập tên tài liệu, mục tiêu, người đọc, ngôn ngữ và giọng văn.
- Bấm Dùng ví dụ nếu muốn bắt đầu nhanh.
- Dán nguồn hoặc nhập PDF/DOCX/TXT/MD. Tối đa 10 MB/tệp, PDF tối đa 100 trang, tổng phần nguồn tối đa 50.000 ký tự.
- PDF scan/ảnh không có lớp văn bản cần OCR trước; ứng dụng chưa có OCR. Chỉ đọc nội dung trong file, chưa tự truy cập URL hoặc tìm nguồn web.
- Chọn OpenAI/Gemini/Claude hoặc AI riêng → Tạo bản thảo theo cấu hình chủ website và hạn mức tài khoản.
- Chỉnh trực tiếp trong Biên tập, hoặc mở Xem trước. Nội dung nhập/AI không được thực thi như HTML/JavaScript.
- Lưu vào thư viện: lần đầu tạo nội dung; các lần sau tạo phiên bản mới. Mở phiên bản cũ rồi Lưu để tạo bản mới từ nó. Nếu hai phiên cùng sửa, server từ chối ghi đè phiên bản mới hơn.
- Xuất Word/DOCX, Markdown hoặc TXT. In/lưu PDF mở hộp in của trình duyệt; chọn Save as PDF/Lưu dưới dạng PDF. Không có PDF renderer server trong build này.
- DOCX xuất theo định dạng cơ bản: tiêu đề, heading và danh sách; Markdown bảng/định dạng nâng cao có thể giữ dạng văn bản, cần chỉnh thêm trong Word.

Nháp đang biên tập được lưu trong trình duyệt; dùng Lưu thư viện để lưu trên backend. Không lưu nháp chỉ trong trình duyệt nếu cần chuyển máy.

## Hình ảnh và video

- Hình ảnh có preset minh họa, bài học, infographic, poster, sản phẩm, ảnh bìa. Nhập chủ đề → Tạo prompt mẫu → chỉnh prompt → Tạo ảnh.
- Ảnh dùng OpenAI/Gemini, được thêm vào Media. Có tải ảnh và lưu ảnh vào thư viện.
- Kiểm tra chữ, sơ đồ và thông tin trong ảnh trước khi dùng; preset không bảo đảm độ chính xác của hình do AI tạo. Chưa có chỉnh sửa ảnh upload, Canvas, tạo ảnh hàng loạt hoặc infographic dữ liệu có kiểm chứng.
- Từ bản thảo, dùng Làm video / Tạo voice / Lên ý tưởng ảnh. Nội dung được chuyển sang bước tiếp theo; chưa có tự dựng video toàn bộ từ văn bản bằng một nút.
- Video Studio giữ các bước kịch bản → chia cảnh → Veo → voice → nhạc/phụ đề → xuất MP4 của V7.7. Voice/nhạc/phụ đề có shortcut từ Video Studio.
- Có lưu các clip Veo và voice vào thư viện. Thư viện mở/xem/nghe/tải; ảnh/video có thể thêm lại vào dự án media.

## Thư viện và dự án

- Thư viện lọc theo loại/lĩnh vực, tìm tiêu đề/nội dung, mở tài liệu hoặc xem tệp.
- Lưu tài liệu/phiên bản ở `.accounts/data/<user-id>/workbench.sqlite3` dưới data-root. Media/voice ở thư mục cùng user. Xóa tệp runtime thì thư viện không khôi phục được.
- Dự án trên máy lưu trạng thái video/media, văn bản đang làm và nguồn vào SQLite. Các tệp media được tham chiếu tại chỗ, chưa được copy thành gói ZIP di động. Mỗi snapshot tối đa 2 MB metadata.
- Dự án GitHub giữ chức năng V7.7 và thêm bản thảo đang làm. Giới hạn tài nguyên 5 MB/tệp, 20 MB/snapshot, cần token Contents read/write.
- Dừng backend/worker, sao lưu toàn bộ data-root gồm `.accounts`, `.ai-company` và pipeline; xem [ARCHITECTURE_VI.md](ARCHITECTURE_VI.md). Không đưa `.env` lên repo công khai.

## Kiểm chứng

Kiểm thử gồm nhập PDF có text/TXT/DOCX, xuất DOCX tiếng Việt, phiên bản/conflict, asset path, persistence sau restart, lưu/khôi phục dự án và provider workflows cũ. Browser kiểm tra mock AI cùng import/export/thư viện/dự án thật, chống thực thi HTML từ nội dung, chuyển công cụ, khôi phục nháp và không tràn ngang mobile.

Các API OpenAI/Gemini/Claude/Veo/GitHub mới vẫn chưa được xác nhận với tài khoản thật vì không có credentials. Skill/template không tự xác nhận chất lượng nội dung chuyên ngành. Ảnh bàn văn bản/mobile trong gói có dữ liệu minh họa từ kiểm thử; không phải kết quả gọi API thật.
