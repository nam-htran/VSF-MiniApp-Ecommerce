# Ngày 1 — Kế hoạch thực thi

> Chưa code gì. Đây là bản ghi việc sẽ làm, để bạn duyệt trước.

## Bối cảnh

Plan.xlsx đặt "Tích hợp V-App" ở ngày 1 (P0) vì hình dạng tích hợp ràng buộc mọi thiết kế phía sau: `user_id` của V-App là khoá định danh, và kết quả thanh toán là **bất đồng bộ qua IPN** chứ không phải giá trị trả về. Làm auth hay checkout trước rồi mới đọc tài liệu thì ngày 7 phải sửa lại.

Ràng buộc thực tế: dự án là intern, **không có quyền truy cập nào** — không `appIdentifier` đã đăng ký, không `client_id`/`client_secret`, không `paymentApiKey`, không Postback URL. Nên cả bốn điểm tích hợp mà Plan liệt kê đều phải mô phỏng.

Mục tiêu chi phối: **mock phải ráp được với API thật bằng thao tác cấu hình**, không phải viết lại. Đó là thứ duy nhất giữ cho công sức 4 tuần không thành code vứt đi.

Chi tiết schema và công thức ký: tra tài liệu gốc tại `developer.v-app.vn` (truy cập bằng `curl` với User-Agent trình duyệt; WebFetch bị chặn 403).

---

## Quyết định kiến trúc

**1. Một repo, hai process.** MiniApp khi deploy là bundle tĩnh (`v-miniapp-cli build` zip `dist` upload lên V-App) — không có server ở đó, nên API bắt buộc là process riêng.

```
v-market/
  package.json          ← MiniApp, GIỮ NGUYÊN Ở GỐC
  app-config.json       ← CLI đọc appIdentifier/version ở đây
  src/                  ← MiniApp
  server/               ← THÊM MỚI: backend V-Market
    src/
      vapp/mock/        ← mô phỏng OpenAPI, chỉ mount khi VAPP_MODE=mock
```

Không di chuyển MiniApp vào `apps/` — `v-miniapp-cli` kỳ vọng `package.json` + `app-config.json` ở gốc và `deploy` xác thực version từ đó. Tái cấu trúc là rước rủi ro vào thứ đang chạy tốt.

**2. Mock nằm trong backend, không phải process thứ ba.** Mount dưới prefix `/__vapp`, chỉ khi `VAPP_MODE=mock`.

Hệ quả tốt: **không cần `MockVAppGateway`**. Chỉ một HTTP client thật, chĩa vào base URL khác nhau:

```bash
VAPP_BASE_URL=http://localhost:3000/__vapp   # hôm nay
VAPP_BASE_URL=https://api.v-app.vn           # ngày có quyền
```

Hai implementation song song là bẫy: bản mock dùng hàng ngày nên luôn đúng, bản real không ai chạy nên luôn sai — và chỉ lộ ra đúng hôm cần ráp.

IPN vẫn là HTTP thật: module mock `POST` tới `/webhooks/vapp/ipn` của chính server — vẫn ký, vẫn retry, vẫn qua tầng verify thật. Cùng process không giảm độ trung thực.

**3. Chốt an toàn:** server **fail ngay lúc khởi động** nếu `NODE_ENV=production` và `VAPP_MODE=mock`. Không có chốt này thì sớm muộn có bản deploy mở toang endpoint cấp token.

---

## Ràng buộc kỹ thuật đã khảo sát

| Phát hiện | Ảnh hưởng |
|---|---|
| `tsconfig.json` có `include: ["src"]`, `moduleResolution: "bundler"`, `noEmit` | `server/` cần tsconfig riêng (`nodenext`, `types: ["node"]`) |
| `erasableSyntaxOnly: true` — cấm enum, parameter properties, namespace | **Không dùng NestJS.** Chọn Fastify (hàm thuần, không decorator) |
| `eslint.config.js` áp `globals.browser` cho toàn repo | Thêm config object scope `server/**/*.ts` với `globals.node`, bỏ rule React |
| `pnpm-workspace.yaml` chỉ có `allowBuilds:`, không có `packages:` | Thêm `packages: ['.', 'server']` |
| `app-config.json` đặt `h5App: "YES"` | Dev preview chạy H5 → `fetch` thường dùng được; `apisAsync.request` để dành cho native |
| `@v-miniapp/apis` v1.0.20 đã có trong `dependencies`, chưa file nào dùng | Dùng cho `RealVAppClient` sau này |

### ⚠️ Một điểm cần kiểm chứng ngay

Type của `@v-miniapp/apis` đã cài khai báo `getAuthCode({ scopes?: ('profile'|'phone'|'email')[] })` — **không có scope `auth`**, trong khi tài liệu `login-free-system` mô tả `auth` là scope cho đăng nhập im lặng.

Hoặc type của SDK lỗi thời, hoặc tài liệu đi trước bản cài. Việc đầu tiên trong ngày là kiểm tra; nếu `auth` thật sự chưa hỗ trợ thì nhánh silent login không demo đúng như tài liệu được, và phải ghi nhận trong báo cáo.

---

## Việc sẽ làm

### A. Dựng khung `server/`
- Thêm `packages: ['.', 'server']` vào `pnpm-workspace.yaml`
- `server/package.json`, `server/tsconfig.json` (nodenext), Fastify + `tsx` cho dev
- Thêm block ESLint scope `server/**/*.ts` với `globals.node`
- `.env.example`; xác nhận `.env` đã nằm trong `.gitignore` (đã có)
- Không dựng DB ở ngày 1 — mock là simulator, lưu trong bộ nhớ là đúng bản chất. Chọn DB là việc của ngày 2 khi làm bảng `users`.

### B. Mock OpenAPI dưới `/__vapp`
- `POST /oauth2/token/exchange`
- `POST /oauth2/token/refresh`
- `GET /open/identity/v1/userinfo`

**Mock phải khắt khe hơn thật, không lỏng hơn.** Chỗ nào tài liệu không nói rõ thì chọn phía nghiêm:

| Yêu cầu | Nếu bỏ qua thì hỏng gì khi ráp thật |
|---|---|
| Envelope `{code, message, data}`, `code: 0` = OK | Code đọc HTTP status thay vì `code` → lỗi thật bị nuốt |
| **Tôn trọng scope**: `auth` chỉ trả `user_id` | Backend quen có sẵn `phone_number`, thật thì thiếu ở checkout |
| authCode dùng **một lần**, TTL 60s | Không ai xử lý `AUTH_CODE_ALREADY_USED` |
| `access_token` hết hạn thật, đúng `expires_in` | Luồng refresh không bao giờ chạy → 401 lúc thật |
| `user_id` là **UUID thật** | Có người parse `"user1"` hoặc dùng làm số |
| `access_token` **opaque** | Có người encode dữ liệu vào token rồi decode ở backend |

### C. Gateway + luồng đăng nhập
- `VAppGateway`: `exchangeAuthCode`, `refreshToken`, `getUserInfo` — **một** bản cài HTTP
- `POST /auth/session`: nhận `authCode` → exchange → userinfo → upsert theo `user_id` → trả JWT V-Market
- Giữ đúng nhánh hai giai đoạn của `login-free-system`: user cũ dừng ở scope `auth`; user mới mới xin `profile phone email` (consent chỉ hiện một lần trong đời mỗi user)
- `role`/`sellerId` là dữ liệu của V-Market, **không** đến từ V-App

### D. Contract test
Một bộ test, chạy được với cả mock và thật:

```bash
VAPP_BASE_URL=http://localhost:3000/__vapp  pnpm test:contract   # hôm nay
VAPP_BASE_URL=https://api.v-app.vn          pnpm test:contract   # ngày có quyền
```

Ca kiểm: authCode hợp lệ → có `user_id`; authCode dùng lại → từ chối; token scope `auth` → **không** có `phone_number`; token hết hạn → 401; refresh → token mới.

Đây là thứ biến "hy vọng ráp được" thành "biết chắc". Ngày có credential, chạy đúng lệnh đó: xanh hết là xong, đỏ chỗ nào là biết chính xác chỗ lệch. Việc này cũng nằm sẵn ở ngày 15 của Plan.

### E. Adapter phía client
```typescript
interface VAppClient {
  getAuthCode(scopes: string[]): Promise<string>;
  initPayment(input: PaymentInput): Promise<void>;   // void: callback không mang kết quả
}
```
- `MockVAppClient` — màn hình chọn tài khoản seed
- `RealVAppClient` — gọi `apis.*`

**Luật:** không component nào được `import apis from '@v-miniapp/apis'` trực tiếp; chỉ `RealVAppClient` được phép. Có luật đó thì ngày ráp thật chỉ đụng một file.

Đây là chỗ **duy nhất** buộc phải có hai implementation — vì mock là trang web còn thật là JSAPI native, khác bản chất chứ không phải khác URL.

---

## Không làm trong ngày 1

- Trang thanh toán giả + IPN sender → **ngày 2**. Ngày 1 chốt hình dạng, ngày 2 dựng.
- Bảng `users` thật, seed buyer/seller A/seller B → ngày 2 (đúng như Plan)
- Shop, sản phẩm, giỏ hàng, tách đơn, tồn kho → ngày 3 trở đi
- COV Order Sync (webhook `order.created/updated/cancelled`) → ngoài phạm vi 4 tuần, cần MuleSoft creds. Ghi vào báo cáo: mô hình COV giả định **một đơn = một seller** (`seller_merchant_id` là scalar, không có `parent_order_id`), nên giỏ đa shop không khớp giả định của nền tảng.

---

## Kiểm chứng

Cuối ngày 1 phải chạy được:

```bash
pnpm --filter server dev            # backend + mock ở :3000

# 1. Lấy authCode (thay getAuthCode)
curl -X POST localhost:3000/__vapp/simulator/authcode \
  -d '{"user_id":"<uuid seed>","scopes":"auth"}'

# 2. Luồng đăng nhập đầy đủ
curl -X POST localhost:3000/auth/session -d '{"authCode":"..."}'
#    → JWT V-Market

# 3. Dùng lại authCode → phải bị từ chối
# 4. Token scope auth → userinfo KHÔNG có phone_number

pnpm test:contract                  # xanh hết
```

Tiêu chí đạt: **luồng `authCode → access_token → user_id → JWT` chạy thật qua HTTP**, và contract test xanh. Đó là bằng chứng cho mốc "Chốt API" của ngày 1.

---

## Đề nghị sửa Plan.xlsx

| Chỗ | Vấn đề | Sửa |
|---|---|---|
| Ngày 1, cột Mốc | Ghi *"API hoạt động"* nhưng ngày 2 mới *"Khởi tạo dự án"* — không thể có code chạy trước khi dự án tồn tại | Kéo phần khởi tạo repo backend lên ngày 1 |
| Ngày 16 | *"Tích hợp V-App **nếu có quyền**"* — điều kiện gần như chắc chắn không xảy ra | Đổi thành: chạy contract test với API thật nếu có; nếu không, bàn giao tài liệu đường ráp |
| Ngày 17 (Optional) | Danh sách có "voucher" | Bỏ — voucher/VPoint thuộc màn hình SDK, không có `paymentApiKey` thì không chạm tới được |

Ngoài ba chỗ đó, nội dung ngày 1 trong Plan là **đúng**: bốn điểm tích hợp được liệt kê trước khi đọc tài liệu (đăng nhập, thông tin người dùng, phiên thanh toán, kết quả thanh toán) trùng khớp với thực tế.
