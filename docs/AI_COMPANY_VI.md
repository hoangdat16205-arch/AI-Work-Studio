# 24 vai trò Kilo

## Bộ nhân viên

Quản lý `ai-manager` và 23 subagent: sản phẩm, nghiệp vụ, kiến trúc, tech lead, UX, UI, frontend, backend, API, database, AI, automation, DevOps, QA lead, test, E2E, bảo mật, quyền riêng tư, hiệu năng, code review, tài liệu, nội dung, duyệt chuyên ngành.

`.kilo/agents/<id>.md` theo định dạng hiện tại; `kilo.jsonc` chọn quản lý. Quản lý chọn người phù hợp, không bắt buộc đủ 24. Lập trình có tester/bảo mật/code review, nội dung có đối chiếu chuyên ngành. Xem diff/lệnh kiểm tra/nguồn trước dùng báo cáo AI.

## Cài từ đầu

1. VS Code: https://code.visualstudio.com/.
2. Extensions → **Kilo Code** chính thức. https://kilo.ai/docs/code-with-ai/platforms/vscode.
3. Node.js LTS theo yêu cầu CLI: https://kilo.ai/docs/code-with-ai/platforms/cli. Chạy:

```sh
npm install -g @kilocode/cli
kilo --version
kilo auth login
```

4. Chọn provider/model Kilo. Key/chi phí độc lập với `.env` web.
5. Mở đúng thư mục giải nén để đọc config/agent, restart phiên sau đổi config.
6. Chọn `ai-manager`, thử “kiểm tra hướng dẫn chạy”. Thiếu model/credit thì chưa thực thi.

Cần hỗ trợ custom agent Markdown và `kilo run --agent --format --attach --file`. Không tạo `.kilocodemodes` cũ.

## Giao việc

Trực tiếp: chọn quản lý, nhập yêu cầu/tiêu chí hoặc đính kèm brief tải từ web. Không worker thì xem kết quả trong Kilo; web không tự đánh dấu hoàn tất.

Qua web:

1. Backend local, đăng ký/cấp admin bằng `tools/manage_accounts.py`.
2. Công ty AI → yêu cầu/lĩnh vực/loại. Kế hoạch mẫu không API; AI lập kế hoạch cần provider và có thể tính phí.
3. Xem task/phụ thuộc → **Giao cho Kilo**; kế hoạch chưa thực thi code.
4. Terminal khác cùng thư mục/môi trường:

```sh
python tools/company_worker.py
```

Windows:

```bat
.venv\Scripts\python.exe tools\company_worker.py
```

5. Worker kiểm tra CLI, nhận mission, chạy Kilo server riêng localhost/mật khẩu, giao quản lý. Helper gửi tiến độ/bằng chứng.
6. “Có báo cáo đạt” cần mọi task có bằng chứng/kết quả đạt, báo cáo cuối hợp lệ và CLI mã 0. Mã 0 thiếu báo cáo vẫn cần kiểm tra.

`--once` một lượt, `--kilo` đường dẫn CLI, `--url` backend loopback (mặc định http://127.0.0.1:5000), `--timeout` 30–7200 giây (mặc định 1800).

## Dừng/quyền

Một checkout thực thi **một mission mỗi lần**. Mức 1/2/4 là mục tiêu prompt, không hard cap. Subagent chung checkout; sửa cùng file phải nối phụ thuộc.

Lease/heartbeat hết hạn đánh dấu ngắt, không tự giao lại. Dừng/hủy còn code đã viết; xem diff trước Giao lại, chưa rollback tự động.

Brief/log/report ở `.ai-company/missions/<id>/` dưới checkout; database/token ở data-root. Không commit runtime/`.env`.

Bridge cần localhost/admin web/token worker; không mở cho khách. Compose tắt bridge server.

Quyền sửa theo vai trò, reviewer chỉ đọc; secrets/runtime và code quyền/tài khoản được bảo vệ. Lệnh khác có thể hỏi quyền Kilo; worker không dùng `--auto`. Chờ quyền chưa hoàn thành.

Agent không tự deploy/push/xử lý secrets. Chủ dự án điều chỉnh quyền có chủ đích nếu cần; phát triển checkout riêng, xem xét rồi phát hành.

Sinh lại:

```sh
python tools/generate_company_agents.py
```

Có thể ghi đè prompt chỉnh tay; nên sửa roster/generator và quản lý Git. Config hiện có được giữ. Nút tải cấu hình đóng gói 24 agent và cấu hình Kilo. Helper/bridge nằm trong gói Studio đầy đủ; chuyển ZIP cấu hình sang repo khác để dùng trực tiếp trong Kilo.

## Kiểm chứng

Đối chiếu 24 frontmatter/config với schema Kilo; test HTTP/subprocess claim/lease/heartbeat/report/thiếu báo cáo. Chưa có CLI/model/credentials của chủ dự án để chạy nhiệm vụ AI thật. Fixture chưa xác nhận chất lượng lập trình hay subagent của model.
