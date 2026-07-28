# Hướng dẫn cấu hình Deploy Backend (Staging & Production)

Tài liệu này hướng dẫn bạn cách thiết lập các biến môi trường trên GitHub Web UI cho Backend FastAPI.

## 1. Cấu hình Biến (Variables)
Trong **Settings > Environments**, chọn từng môi trường để thêm các biến sau:

### Môi trường `staging`
- `API_PORT`: `8001` (Cổng chạy API cho staging)
- `CORS_ORIGINS`: `https://app-staging.solodesk.space,http://localhost:5173` (Thêm localhost để dev FE tại máy cá nhân có thể gọi vào API Staging)

### Các biến bổ trợ (Third-party)
Cần thiết lập cho cả 2 môi trường để các tính năng AI, Login Google và Thanh toán hoạt động:

| Loại | Tên Biến | Ghi chú |
| :--- | :--- | :--- |
| **Secrets** | `GOOGLE_CLIENT_ID` | Lấy từ Google Cloud Console |
| **Secrets** | `GOOGLE_CLIENT_SECRET` | Lấy từ Google Cloud Console |
| **Variables** | `GOOGLE_REDIRECT_URI` | Ví dụ: `https://api.solodesk.space/api/v1/auth/google/callback` |
| **Secrets** | `GROQ_API_KEY` | **Bắt buộc** — mọi tính năng AI (chấm điểm deal, soạn báo giá, soạn hợp đồng, viết lời nhắc) đều chạy qua Groq. Thiếu là AI chết hẳn. |
| **Secrets** | `OPENAI_API_KEY` | Tuỳ chọn, hiện chưa module AI nào dùng tới |
| **Secrets** | `STRIPE_SECRET_KEY` | Mã từ Stripe (sk_test_... cho staging) |
| **Secrets** | `STRIPE_WEBHOOK_SECRET` | Mã xác thực Webhook của Stripe |

### Kho lưu file đính kèm (Object storage) — BẮT BUỘC

File khách gửi kèm deal (brief PDF, hợp đồng scan, biên nhận) nằm trên MinIO chạy ngay
trong stack (`compose.deploy.yml`). Không có mấy biến này thì **service `minio` không
khởi động nổi và cả lệnh deploy sẽ dừng lại** — cố ý như vậy, vì lần trước thiếu cấu hình
storage mà deploy vẫn báo xanh, người dùng upload file nào cũng nhận 409 và AI chấm deal
nào cũng ra 0/100 do không có gì để đọc.

| Loại | Tên Biến | Giá trị |
| :--- | :--- | :--- |
| **Secrets** | `STORAGE_ACCESS_KEY` | Tự đặt, tối thiểu 5 ký tự. **Đừng dùng lại `solodesk` của môi trường local.** |
| **Secrets** | `STORAGE_SECRET_KEY` | Tự đặt, tối thiểu 8 ký tự, nên dài và ngẫu nhiên |
| **Variables** | `STORAGE_BUCKET` | `solodesk-uploads` |

`STORAGE_ENDPOINT` (`http://minio:9000`) và `STORAGE_REGION` đã ghi cứng trong workflow,
không cần khai trên GitHub.

> **Thứ tự quan trọng:** thêm 3 biến trên **trước** khi merge, nếu không lần deploy kế
> tiếp sẽ dừng ở bước `docker compose up` với lỗi `STORAGE_ACCESS_KEY is required`.

Dữ liệu nằm trong Docker volume `<project>_minio_data`. **Xoá volume này là mất toàn bộ
file khách đã gửi** — cân nhắc backup định kỳ cho production.

### Môi trường `production`
- `API_PORT`: `8000` (Cổng mặc định cho production)
- `CORS_ORIGINS`: `https://app.solodesk.space` (Cho phép Frontend chính thức gọi vào)

## 2. Thiết lập Manual Approval (Duyệt thủ công)
Tương tự như Web, bạn nên bật tính năng này cho Backend để kiểm soát việc lên Production:
1. Vào **Settings** -> **Environments** -> **production**.
2. Tích chọn **Required reviewers**.
3. Thêm tên tài khoản của bạn.
4. Nhấn **Save**.

## 3. Các bước kiểm tra
1. Sau khi deploy xong Staging, hãy thử mở Frontend Staging và thực hiện đăng nhập/thao tác.
2. Nếu Frontend báo lỗi "CORS error", hãy kiểm tra lại biến `CORS_ORIGINS` trên GitHub xem đã đúng domain staging chưa.
3. Kiểm tra logs container trên server: `docker compose logs -f api` để xem API đang chạy ở cổng nào.
4. **Kiểm tra kho file** — tuyệt đối đừng chỉ tin deploy báo xanh, vì `/health/ready` không hề chạm tới storage:
   ```bash
   docker compose -p solodesk-backend-staging -f compose.deploy.yml logs api | grep -i storage
   ```
   Thấy `storage.disabled_in_deployed_env` là cấu hình còn thiếu. Sau đó thử tạo một deal
   có đính kèm PDF trên giao diện, mở lại Detail phải thấy file.

## 4. Lưu ý về CORS
Trong code (`backend/src/config/settings.py`), tôi đã để mặc định là `*` nếu không có biến môi trường, nhưng khi chạy qua GitHub Actions, biến `CORS_ORIGINS` từ GitHub Vars sẽ được ưu tiên để đảm bảo bảo mật.
