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
| **Secrets** | `OPENAI_API_KEY` | Mã API từ OpenAI |
| **Secrets** | `STRIPE_SECRET_KEY` | Mã từ Stripe (sk_test_... cho staging) |
| **Secrets** | `STRIPE_WEBHOOK_SECRET` | Mã xác thực Webhook của Stripe |

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

## 4. Lưu ý về CORS
Trong code (`backend/src/config/settings.py`), tôi đã để mặc định là `*` nếu không có biến môi trường, nhưng khi chạy qua GitHub Actions, biến `CORS_ORIGINS` từ GitHub Vars sẽ được ưu tiên để đảm bảo bảo mật.
