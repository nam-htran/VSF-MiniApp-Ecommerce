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

### Đăng nhập bằng vai trò vận hành

Màn hình *Đối soát thanh toán* chỉ mở cho tài khoản có vai trò `ADMIN`. Vai
trò này đến từ **config, không phải từ database** — không có admin nào để
cấp quyền cho admin đầu tiên, và một endpoint "cho tôi làm admin" là đúng
thứ không nên xây.

```bash
# server/.env
ADMIN_VAPP_USER_IDS=44444444-4444-4444-8444-444444444444
```

Tài khoản đó (`Phạm Vận Hành`) có sẵn trong mock. Đăng nhập bằng nó là thấy
mục *Đối soát thanh toán* trong tab Tài khoản.

---

## Vì sao có `mock-openAPI`

Dự án **không có quyền truy cập DevCenter** của V-App, nên không lấy được
`clientId`/`clientSecret` thật. `mock-openAPI` dựng lại đúng những gì V-App
cung cấp — đổi `authCode` lấy phiên, hồ sơ người dùng, và một cổng thanh
toán biết gửi **IPN có ký** về server.

Nhờ vậy toàn bộ luồng chạy được thật, và khi có credential thật thì chỉ đổi
`VAPP_BASE_URL`. Chi tiết: [docs/phase1/day1/login.md](docs/phase1/day1/login.md).

---

## Tài liệu

Sắp theo **ngày trong Plan**, để một dòng kế hoạch tra ngược ra được tài liệu
và ngược lại.

| Ngày | | |
|---|---|---|
| 1 | [day1/login.md](docs/phase1/day1/login.md) | Đăng nhập qua V-App, consent hai giai đoạn |
| 2 | [day2/research.md](docs/phase1/day2/research.md) | Khảo sát nền tảng |
| 2 | [day2/storage.md](docs/phase1/day2/storage.md) | Vì sao Postgres |
| — | [day3/platform-constraints.md](docs/phase1/day3/platform-constraints.md) | **Ràng buộc của V-App — đọc trước khi thêm tính năng** |
| 3 | [day3/shops.md](docs/phase1/day3/shops.md) | Shop và vai trò |
| 4 | [day3/products.md](docs/phase1/day3/products.md) | Sản phẩm |
| 5–6 | [day5/buyer-journey.md](docs/phase1/day5/buyer-journey.md) | Duyệt hàng, tìm kiếm, danh mục, giỏ hàng |
| 7 | [day7/checkout.md](docs/phase1/day7/checkout.md) | Sổ địa chỉ, định vị, báo giá, đặt hàng |
| 8, 11–12 | [day3/orders.md](docs/phase1/day3/orders.md) | Đơn hàng, thanh toán, giữ hàng, **bảo vệ tiền người mua** |
| 9 | [day9/fulfilment-and-storefront.md](docs/phase1/day9/fulfilment-and-storefront.md) | Người bán xử lý đơn, trang cửa hàng, upload ảnh |
| 13 | [day13/security.md](docs/phase1/day13/security.md) | Phân quyền, kiểm duyệt, XSS, rate limit |
| 14 | [day3/frontend.md](docs/phase1/day3/frontend.md) | Kiến trúc MiniApp |
| 15 | [day15/testing.md](docs/phase1/day15/testing.md) | Cách kiểm thử và ma trận 57 ca |
| 17 | [day3/vouchers-variants.md](docs/phase1/day3/vouchers-variants.md) | Voucher, phân loại, SKU |
| 17 | [day17/reviews.md](docs/phase1/day17/reviews.md) | Đánh giá của người đã mua |

> Thư mục `day3/` chứa cả tài liệu của ngày sau (`orders.md`,
> `vouchers-variants.md`, `frontend.md`). Chúng lớn dần theo thời gian và
> được giữ nguyên chỗ để link cũ không hỏng — cột **Ngày** ở trên mới là
> chỗ tra đúng.

`Plan.xlsx` có kế hoạch 4 tuần và **ma trận 57 ca kiểm thử**, mỗi ca ghi rõ
file test chứng minh nó.

### Phase 2 — AI Recommendation

| Tài liệu | Nội dung |
|---|---|
| [Proposal_Phase_2.docx](Phase_2_docs/Proposal_Phase_2.docx) | Phạm vi, mô hình, trạng thái và phần còn lại trước release |
| [Plan_Phase_2.xlsx](Phase_2_docs/Plan_Phase_2.xlsx) | Execution plan và verification matrix đã cập nhật |
| [Architecture.docx](Phase_2_docs/Architecture.docx) | Kiến trúc offline, semantic indexer, Transformer mask và serving |
| [Architecture.png](Phase_2_docs/Architecture.png) | Sơ đồ kiến trúc tổng thể |
| [Architecture_RQ-VAE.png](Phase_2_docs/Architecture_RQ-VAE.png) | Sơ đồ residual quantization ba tầng |
| [SUMMARY_4PAPER.md](Phase_2_docs/Docs/SUMMARY_4PAPER.md) | Tổng hợp TIGER, GR4AD, CQ-SID và TSGR |

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
  huỷ — xem [orders.md §6](docs/phase1/day3/orders.md#6-tiền-của-người-mua).
- **Tồn kho nằm ở đúng một nơi**: trên sản phẩm, hoặc trên phân loại, không
  bao giờ cả hai.

---

## Kiểm thử

```bash
cd server
.venv/Scripts/python.exe -m pytest              # 150 ca
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
  `payment_exceptions` và hiện ở màn hình *Đối soát thanh toán*; việc hoàn
  vẫn là thao tác tay, màn hình chỉ ghi nhận đã hoàn để không hoàn hai lần.
- **Rate limit và scheduler chạy in-process** — nhiều worker thì mỗi worker
  một bản. Production cần Redis hoặc leader lock.
- Ảnh demo nằm trong bundle; sản phẩm thật sẽ dùng ảnh upload.
