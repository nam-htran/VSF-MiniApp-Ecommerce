# V-Market MiniApp

Frontend React 19 của V-Market, xây bằng `@v-miniapp/ui-react`,
`@v-miniapp/apis`, Tailwind CSS và V MiniApp CLI.

## Trải nghiệm chính

- Trang chủ, tìm kiếm, flash sale, gian hàng và chi tiết sản phẩm.
- Recommendation cá nhân theo lịch sử xem và related products theo Semantic ID.
- Giỏ hàng nhiều shop, biến thể, voucher, checkout và theo dõi đơn.
- Kênh người bán quản lý shop, sản phẩm, voucher và xử lý đơn.
- Màn hình vận hành đối soát ngoại lệ thanh toán.

Routing dùng path một tầng và query parameter, ví dụ `/product?id=...`. Request
đi qua `@v-miniapp/apis` trên thiết bị HTTPS; Simulator local dùng browser fetch
tới `http://127.0.0.1:4000`.

## Chạy toàn bộ demo

Từ thư mục này:

```bash
pnpm install
pnpm dev
```

Script `scripts/dev-all.mjs` sẽ:

1. Khởi động PostgreSQL bằng Docker Compose.
2. Tạo Python venv trong lần chạy đầu và chạy Alembic migration.
3. Mở mock-openAPI ở `4001` và backend ở `4000`.
4. Seed catalog demo khi database đang rỗng.
5. Mở V MiniApp CLI Simulator ở `3000`.

Dự án không có quyền DevCenter, nên dev script chỉ mint một local stand-in token
để CLI Simulator khởi động. Token này không thể deploy. Nếu máy đã đăng nhập
V MiniApp CLI thật, credential thật luôn được ưu tiên.

## Chạy riêng frontend

```bash
pnpm dev:app
```

Biến môi trường:

```text
VITE_API_BASE=http://127.0.0.1:4000
VITE_VAPP_BASE=http://127.0.0.1:4001
```

## Kiểm tra và build

```bash
pnpm exec tsc --noEmit
pnpm lint
pnpm build
```

`pnpm build` gọi `v-miniapp-cli build` và tạo bundle trong `dist/`. Deploy thật
cần V-ID login, `appIdentifier` đã đăng ký và quyền DevCenter; local demo không
cần các quyền đó.
