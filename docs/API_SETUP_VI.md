# Kết nối API chính thức — AI Work Studio V8.3

Bản này gọi API từ Flask/Python. Key/token chỉ nằm trong `.env` trên máy backend. Gói ZIP không có key thật. Trạng thái “Đã cấu hình” chỉ xác nhận đã có biến môi trường; bấm **Kiểm tra API** để xác nhận key và quyền đọc model. Việc tạo nội dung còn phụ thuộc billing, quota, khu vực và quyền model.

## 1. Google Gemini và Veo: lấy đúng credentials trước khi gọi

Bản build này sử dụng **Gemini API qua Google AI Studio**, không dùng endpoint Vertex AI. Endpoint được xác minh từ tài liệu chính thức bên dưới; không cần nhập một URL API do dịch vụ bên thứ ba cung cấp.

1. Đăng nhập https://aistudio.google.com/apikey.
2. Tạo hoặc chọn Google Cloud project của bạn và tạo API key cho Gemini API. Nếu key có API restrictions, kiểm tra nó cho phép Generative Language API; các giới hạn IP phải cho phép máy backend.
3. Trong Google AI Studio, kiểm tra project đang ở paid tier/billing và có quyền sử dụng Veo. Việc Gemini viết được văn bản không tự xác nhận rằng Veo đã được cấp quyền.
4. Mở tài liệu model Veo https://ai.google.dev/gemini-api/docs/veo và chọn model có trong tài khoản. Tài liệu kiểm tra trong lần build này có `veo-3.1-generate-preview` và `veo-3.1-fast-generate-preview`. Veo 3.0 được đánh dấu deprecated. Bạn có thể thay VEO_MODEL bằng ID chính thức phù hợp.
5. Mở `.env` và điền:

```env
GEMINI_API_KEY=YOUR_GOOGLE_API_KEY
GEMINI_API_MODE=interactions
GEMINI_MODEL=gemini-3.8-flash
GEMINI_IMAGE_MODEL=gemini-3.1-flash-image
GEMINI_TTS_MODEL=gemini-3.8-flash-tts
VEO_MODEL=veo-3.1-generate-preview
```

Các model mặc định được lấy từ tài liệu tại thời điểm build. Nếu tài khoản không có model đó, chọn ID đang được Google cấp quyền và cập nhật `.env`. Chế độ tương thích `GEMINI_API_MODE=generate_content` sử dụng `models/{MODEL}:generateContent` cho văn bản/ảnh; hãy chọn model hỗ trợ API tương ứng. Gemini TTS hiện dùng Interactions.

6. Khởi động lại `start_windows.bat`, mở **AI Studio**, bấm **Kiểm tra API** trên Gemini và Veo. Kiểm tra này đọc metadata model, không tạo clip.
7. Thử **một cảnh** trước để kiểm tra quyền tạo clip, quota và kết quả, sau đó tăng số cảnh khi cần. Lệnh Tạo clip dùng API có thể tính phí theo tài khoản Google.

Endpoint REST Veo trong tài liệu Google:

```text
POST https://generativelanguage.googleapis.com/v1beta/models/{VEO_MODEL}:predictLongRunning
Header: x-goog-api-key: <GEMINI_API_KEY>
Content-Type: application/json

GET https://generativelanguage.googleapis.com/v1beta/{operation.name}
Header: x-goog-api-key: <GEMINI_API_KEY>
```

Body bản build gửi:

```json
{
  "instances": [{"prompt": "Your scene prompt"}],
  "parameters": {
    "aspectRatio": "16:9",
    "durationSeconds": 8,
    "resolution": "720p"
  }
}
```

Khi operation có `done: true`, URI clip nằm trong `response.generateVideoResponse.generatedSamples[0].video.uri`. Backend tải từ URI Google trả về; key chỉ được gửi đến host Generative Language API. Không tự dựng URL file hay dùng API Veo không chính thức.

Tác vụ lưu trong `veo_jobs/`. Sau khi restart backend, bấm **Tiếp tục tác vụ Veo** để kiểm tra operation đã lưu. Các cảnh hoàn tất không được gửi lại. Nếu kết quả POST ban đầu không xác định do mất mạng/timeout, ứng dụng từ chối tự gửi lại; kiểm tra tài khoản Google để tránh gửi trùng. Clip hoàn tất trước lỗi vẫn xuất hiện trong media. Mỗi batch tối đa 12 cảnh, tối đa 2 batch đang chạy, mỗi clip 8 giây. Bản này chưa có image-to-video/reference images, extension, Vertex AI hoặc hủy operation.

Nguồn:
- Veo: https://ai.google.dev/gemini-api/docs/veo
- Gemini text: https://ai.google.dev/gemini-api/docs/text-generation
- Interactions: https://ai.google.dev/gemini-api/docs/interactions
- Ảnh: https://ai.google.dev/gemini-api/docs/image-generation
- TTS: https://ai.google.dev/gemini-api/docs/speech-generation

## 2. OpenAI / ChatGPT

1. Tạo API key tại https://platform.openai.com/api-keys.
2. Cấu hình billing/quota cho project API và quyền các model muốn sử dụng. Gói ChatGPT trên web không tự cung cấp credit API cho ứng dụng Flask.
3. Điền `.env`, sau đó restart backend:

```env
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
OPENAI_MODEL=gpt-4.1-mini
OPENAI_IMAGE_MODEL=gpt-image-1
OPENAI_TTS_MODEL=gpt-4o-mini-tts
```

4. **AI Studio → OpenAI → Kiểm tra API**. Model mặc định có thể đổi sang model được cấp quyền trong project. Kiểm tra quyền model văn bản không xác nhận quyền tạo ảnh hoặc giọng đọc.

Đã nối: Responses API cho kịch bản, sửa, dịch, tiêu đề/mô tả/hashtag và chia cảnh; Images API tạo ảnh; Audio Speech API tạo giọng. 13 giọng xuất hiện trong Voice sau khi có key. OpenAI ảnh hỗ trợ kích thước 1536×1024 hoặc 1024×1536; tỷ lệ đầu vào 16:9/9:16 được ánh xạ gần nhất và fit vào khung khi dựng video. Không có OpenAI video/Sora trong build này.

Nguồn:
- https://platform.openai.com/docs/api-reference/responses/create
- https://platform.openai.com/docs/guides/image-generation
- https://platform.openai.com/docs/guides/text-to-speech

## 3. Anthropic Claude

1. Tạo key trong https://platform.claude.com/settings/keys và cấu hình billing API.
2. Chọn model ID có quyền trên tài khoản; gói Claude chat không tự cung cấp credit API.
3. Điền và restart backend:

```env
ANTHROPIC_API_KEY=YOUR_ANTHROPIC_API_KEY
CLAUDE_MODEL=claude-sonnet-4-6
```

Claude dùng Messages API để viết/sửa/dịch kịch bản, tạo tiêu đề và chia cảnh/prompt. Tạo ảnh/video/audio dùng provider tương ứng ở bước sau.

Nguồn: https://platform.claude.com/docs/en/api/messages/create

## 4. GitHub: đọc/ghi dự án và tài nguyên

1. Tạo repository riêng của bạn. Khởi tạo README để repo có branch và ít nhất một commit.
2. Tạo fine-grained personal access token tại https://github.com/settings/personal-access-tokens.
3. Chọn đúng repository và cấp **Contents: Read and write**. Repo trong tổ chức có thể cần phê duyệt token/SSO theo chính sách của tổ chức.
4. Điền `.env`:

```env
GITHUB_TOKEN=YOUR_FINE_GRAINED_PAT
GITHUB_REPO=your-account/your-repository
GITHUB_BRANCH=main
GITHUB_PROJECTS_PATH=ai-video-studio
```

5. Restart backend. Mở **Dự án GitHub → Kiểm tra kết nối**.
6. Nhập mã dự án, ví dụ `du-lich-da-lat`.
7. **Lưu dự án lên GitHub** tạo một commit snapshot gồm kịch bản, cảnh, SRT, voice, media, nhạc và một số cài đặt dựng. **Tải dự án từ GitHub** phục hồi chúng vào ứng dụng.

Nếu mã dự án đã tồn tại, phải tải dự án trước khi lưu cập nhật. Nếu người khác cập nhật dự án/branch trong lúc bạn chỉnh, ứng dụng từ chối ghi đè và không force-push. Repo có protected branch có thể từ chối ghi; chọn branch cho phép token cập nhật.

Giới hạn ứng dụng: 5 MB mỗi tệp, 20 MB toàn snapshot, 100 tài nguyên. Các tệp vượt giới hạn làm lần lưu thất bại trước khi upload. Clip Veo lớn cần lưu riêng hoặc giảm kích thước. Snapshot mới không tự xóa các blob/tài nguyên cũ trong repo. `.env`, API key, venv và tệp hệ thống không được snapshot. Nên dùng private repo nếu nội dung chưa muốn công khai.

Nguồn:
- https://docs.github.com/en/rest/repos/contents
- https://docs.github.com/en/rest/git

## 5. Luồng sử dụng

1. **AI Studio → Viết kịch bản → Dùng làm kịch bản**.
2. Chọn số cảnh → **AI chia cảnh**; hoặc **Chia thủ công** rồi viết prompt. Kiểm tra/sửa lời thoại và prompt. AI chia cảnh phải giữ đủ lời thoại gốc; backend báo lỗi nếu lời thoại đã bị đổi/bỏ.
3. Tạo ảnh cho cảnh hoặc chọn các cảnh và **Tạo clip**. Veo hỗ trợ khung 16:9/9:16 trong build này.
4. Chọn giọng trong Voice, quay lại AI Studio → **Tạo voice theo cảnh**.
5. Trong Media, dùng đúng các clip tương ứng theo thứ tự cảnh. Khi scene IDs của media khớp scene IDs của voice, pipeline dựng theo thời lượng lời thoại từng cảnh (clip được lặp nếu lời thoại dài hơn 8 giây). Nếu trộn thêm media khác, pipeline chia đều thời lượng như bản trước.
6. Thêm nhạc → tạo/chỉnh SRT → xuất MP4. Âm thanh gốc của clip Veo không được trộn; pipeline dùng voice/nhạc đã chọn.
7. Lưu dự án GitHub khi cần. Key/token không đi theo dự án.

## Hyperframes

Chưa có URL, API specification hoặc repository cụ thể của Hyperframes trong yêu cầu. Bản build này không tạo endpoint Hyperframes giả định. Khi xác định được dự án/dịch vụ cụ thể, có thể thêm adapter theo tài liệu của nó.

## Kiểm chứng và giới hạn

API mới được kiểm tra bằng mock; không có credentials nên chưa gọi OpenAI/Gemini/Claude/Veo/GitHub thật trong phiên build. Các test không xác nhận quota hoặc model access của tài khoản bạn. API tạo nội dung không tự retry khi lỗi để tránh tạo yêu cầu tính phí trùng.

V8.3 có đăng nhập/dữ liệu riêng. GitHub ghi repo dành cho admin; ảnh/Veo/giọng API thuộc Pro. Key chủ website dùng chung cho yêu cầu được phép, cần hạn mức theo chi phí. Công khai qua HTTPS/reverse proxy, bật cookie Secure, tắt Kilo bridge. AI riêng: [ARCHITECTURE_VI.md](ARCHITECTURE_VI.md); Pro/PayOS: [ACCOUNTS_PRO_VI.md](ACCOUNTS_PRO_VI.md).
