# mock-openAPI

Mock service thay thế phần V-App mà dự án không thể gọi khi chưa có tài khoản
DevCenter. Nó giúp luồng local dùng đúng biên hệ thống: V-Market chỉ nhận
`authCode`, access token và IPN; backend không tự tạo mật khẩu hay giả lập danh
tính bên trong database của mình.

Mock có database `vapp_mock` riêng, tách khỏi database `vmarket`.

## API được mô phỏng

| Method | Endpoint | Vai trò |
|---|---|---|
| `POST` | `/oauth2/token/exchange` | Đổi `authCode` lấy access token |
| `POST` | `/oauth2/token/refresh` | Làm mới access token |
| `GET` | `/open/identity/v1/userinfo` | Trả thông tin đúng theo scope đã cấp |
| `POST` | `/simulator/payment/init` | Khởi tạo phiên thanh toán local |
| `POST` | `/simulator/payment/{id}/confirm` | Xác nhận và gửi IPN có chữ ký tới merchant |

Các endpoint `/simulator/*` là công cụ demo, không tồn tại trong V-App thật.
Chúng tạo user, phát `authCode`, mô phỏng xác nhận/bỏ thanh toán và cấu hình lỗi
để kiểm thử retry/reconciliation.

`authCode` dùng một lần và hết hạn sau 60 giây. Access token là opaque token,
không nhúng `user_id`; scope `auth` không tự động cấp profile hoặc phone.

Swagger chạy tại <http://127.0.0.1:4001/docs>.

## Chạy

Thông thường chỉ cần chạy toàn bộ stack:

```bash
cd ../v-market
pnpm dev
```

Để chạy mock riêng:

```bash
docker compose up -d --wait

cd mock-openAPI
cp .env.example .env
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn main:app --port 4001 --reload
```

`CLIENT_ID`, `CLIENT_SECRET` và `PAYMENT_IPN_SECRET` phải khớp với `server/.env`.
Khi có credential V-App thật, đổi `VAPP_BASE_URL` ở backend và dừng service này;
backend không có nhánh logic mock/real riêng.
