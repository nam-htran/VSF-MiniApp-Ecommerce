# V-Market

Sàn thương mại điện tử nhiều người bán, chạy như một **V-MiniApp** trên nền
tảng V-App của Vingroup.

Một người mua duyệt hàng của nhiều shop, bỏ chung một giỏ, trả tiền **một
lần**, và mỗi shop tự giao phần của mình. Người bán mở shop, đăng sản phẩm,
chạy mã giảm giá và xử lý đơn của riêng họ.

---

## Chạy thử

Cần **Docker** (Postgres nằm trong đó) và **Node + pnpm**.

```bash
cd v-market
pnpm install
pnpm dev          # dựng venv nếu chưa có, rồi chạy cả 3 tiến trình
```

`pnpm dev` khởi động:

| | Cổng | Là gì |
|---|---|---|
| MiniApp | 3000 | giao diện, Vite dev server |
| Backend | 4000 | FastAPI + Postgres |
| mock-openAPI | 4001 | **giả lập V-App**: đăng nhập và cổng thanh toán |

Nạp dữ liệu mẫu (6 shop, 30 sản phẩm, đánh giá thật):

```bash
cd server
.venv/Scripts/python.exe scripts/seed_demo.py
```

Mở http://localhost:3000.

---

## Vì sao có `mock-openAPI`

Dự án **không có quyền truy cập DevCenter** của V-App, nên không lấy được
`clientId`/`clientSecret` thật. `mock-openAPI` dựng lại đúng những gì V-App
cung cấp — đổi `authCode` lấy phiên, hồ sơ người dùng, và một cổng thanh
toán biết gửi **IPN có ký** về server.

Nhờ vậy toàn bộ luồng chạy được thật, và khi có credential thật thì chỉ đổi
`VAPP_BASE_URL`. Chi tiết: [docs/day1/login.md](docs/day1/login.md).

---

## Tài liệu

| | |
|---|---|
| [day1/login.md](docs/day1/login.md) | Đăng nhập qua V-App, consent hai giai đoạn |
| [day2/research.md](docs/day2/research.md) | Khảo sát nền tảng |
| [day2/storage.md](docs/day2/storage.md) | Vì sao Postgres |
| [day3/platform-constraints.md](docs/day3/platform-constraints.md) | Ràng buộc của V-App — đọc trước khi thêm tính năng |
| [day3/shops.md](docs/day3/shops.md) | Shop và vai trò |
| [day3/products.md](docs/day3/products.md) | Sản phẩm |
| [day3/orders.md](docs/day3/orders.md) | Đơn hàng, thanh toán, giao hàng, **và bảo vệ tiền người mua** |
| [day3/vouchers-variants.md](docs/day3/vouchers-variants.md) | Voucher, phân loại, SKU, kiểm duyệt |
| [day3/frontend.md](docs/day3/frontend.md) | Giao diện |

`Plan.xlsx` có kế hoạch 4 tuần và **ma trận 57 ca kiểm thử**, mỗi ca ghi rõ
file test chứng minh nó.

---

## Vài quyết định đáng đọc

Những thứ dễ làm sai và đã được cân nhắc kỹ:

- **Tiền và tồn kho không bao giờ đến từ client.** Giá đọc lại từ DB trong
  đúng giao dịch khoá tồn kho.
- **Một hàm tính giảm giá duy nhất.** Giá trên card, báo giá, và tiền thật
  bị trừ đều đi qua nó — không thể quảng cáo một đằng tính một nẻo.
- **Đơn chỉ `PAID` khi IPN server-to-server tới.** Khách mất mạng không ảnh
  hưởng gì.
- **Giữ hàng có thời hạn**, và đơn đang được thanh toán thì **không** bị
  huỷ — xem [orders.md §6](docs/day3/orders.md#6-tiền-của-người-mua).
- **Tồn kho nằm ở đúng một nơi**: trên sản phẩm, hoặc trên phân loại, không
  bao giờ cả hai.

---

## Kiểm thử

```bash
cd server
.venv/Scripts/python.exe -m pytest              # 133 ca
.venv/Scripts/python.exe -m pytest -m "not slow"  # bỏ nhóm tải
```

Cần cả Postgres lẫn `mock-openAPI` đang chạy — test đi qua HTTP thật, không
mock tầng nào.

> Bộ test **truncate** mọi bảng nó đụng tới. Chạy xong thì seed lại nếu còn
> muốn dùng dữ liệu demo.

Frontend: `cd v-market && npx tsc --noEmit`.

---

## Chưa làm

Ghi ra để không ai tưởng là đã có:

- **Chưa deploy** ở đâu cả — chỉ chạy local.
- **Chưa có hoàn tiền tự động.** Tiền không áp được thì ghi vào
  `payment_exceptions`; hoàn là thao tác tay.
- **Rate limit và scheduler chạy in-process** — nhiều worker thì mỗi worker
  một bản. Production cần Redis hoặc leader lock.
- **Chưa có vai trò admin**, nên `payment_exceptions` chưa có màn hình.
- Ảnh demo nằm trong bundle; sản phẩm thật sẽ dùng ảnh upload.
