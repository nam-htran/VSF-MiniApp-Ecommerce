# Ràng buộc của nền tảng V-App

Tổng hợp từ `developer.v-app.vn`, hai skill trong `.claude/skills/`, và đọc trực tiếp code trong `node_modules/@v-miniapp/`.

Ký hiệu nguồn:

- **[Tài liệu]** — trích nguyên văn, có URL
- **[Code]** — đọc từ package đã cài, chính xác hơn tài liệu
- **[Suy luận]** — tôi suy ra, chưa kiểm chứng

---

## 0. Trạng thái hiện tại

`v-market/` **đã được scaffold** bằng template `react-tailwind`: React 19.2.3, Vite 7, `@v-miniapp/ui-react@1.0.79`, `@v-miniapp/apis@1.0.20`. Có sẵn `src/app.config.ts` với 3 trang mẫu.

CLI **đã đăng nhập** (`v-miniapp-cli whoami` trả về tài khoản VSF), nên `dev` chạy được ngay.

Còn thiếu: `app-config.json` vẫn là `"YOUR_APP_ID"` / `"YOUR_APP_NAME"`.

---

## 1. Không có `fetch`, không có `XMLHttpRequest`

Ràng buộc kỹ thuật lớn nhất.

> **[Tài liệu]** `/api/network/request` — "Ứng dụng của bạn sẽ được chạy trong môi trường cô lập thuần javascript nên sẽ không có các hàm gọi network thông thường như `fetch` hay `XMLHttpRequest`. Để thực hiện gọi network bạn phải dùng đến `request`."
>
> "**Hiện chỉ hỗ trợ những request qua giao thức https.**"

**[Code]** `@v-miniapp/apis/dist/types/request.d.ts`:

```ts
type IVsfRequestOptions = {
  url: string
  method?: string                 // mặc định 'GET'
  headers?: Record<string, string>
  data?: any
  timeout?: number                // ms, mặc định 30000
  dataType?: string               // 'JSON' | 'text' | 'base64' | 'arraybuffer'
  includeHeader?: boolean
  stepup?: boolean                // kích hoạt StepUp authentication
}
```

Loại bỏ: axios, và mọi thư viện fetch dữ liệu dùng adapter mặc định. TanStack Query vẫn dùng được vì nó không gắn với transport — chỉ cần tự viết `queryFn`.

**Hệ quả bắt buộc:** một module duy nhất chọn URL và transport.

```ts
// src/api/client.ts — nơi DUY NHẤT quyết định gọi mạng thế nào
const BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:4000'

export async function apiRequest<T>(path: string, init = {}): Promise<T> {
  const res = await apisAsync.request({ url: `${BASE}${path}`, dataType: 'JSON', ...init })
  return res.data as T
}
```

### `apisAsync` ném lỗi ngoài môi trường V-App

**[Code]** `@v-miniapp/apis/dist/api/index.js` — bridge là `new Proxy({}, { get(_, o) { return window.vsf[o] ... } })`, truy cập `window.vsf` **không có guard**. Chạy trong tab trình duyệt thường, trong test, hoặc SSR đều nhận `TypeError: Cannot read properties of undefined`.

Nên cần một lớp bọc phát hiện năng lực (`typeof window !== 'undefined' && window.vsf`) nếu muốn chạy unit test hay Storybook.

---

## 2. Whitelist domain

> **[Tài liệu]** `/development/devcenter/whitelist-domain` — "các Mini App chỉ được phép giao tiếp với các máy chủ bên ngoài đã được khai báo và xác thực. Bất kỳ request nào gửi đến các tên miền không nằm trong danh sách an toàn này đều sẽ **bị nền tảng chặn tự động**."

Điều kiện đăng ký:

- Bắt buộc `https://` hoặc `wss://`
- **Từ chối chứng chỉ tự ký** — "chứng chỉ tự ký - self-signed... Backend sẽ từ chối kết nối"
- Phải phục vụ file `vsf-verification.txt` ở gốc public để VSF gọi vào xác minh

> "Các tên miền mới được cấu hình thành công sẽ chỉ áp dụng cho các bản build được upload **sau** thời điểm thêm tên miền... **Bạn bắt buộc phải tạo và upload một bản build mới**."

Whitelist **bind vào bản build**. Thêm domain sau thì phải build lại.

### `127.0.0.1:4000` chạy được ở đâu

| Môi trường | Kết quả | Cơ chế |
|---|---|---|
| `v-miniapp-cli dev` | ✅ chạy | proxy Node trên máy dev |
| DevAssistant trên máy thật | ❌ chết | bridge native; sai host **và** HTTP bị từ chối |
| Production | ❌ chết | HTTPS + whitelist |

**[Code]** `@v-miniapp/cli/dist/plugins/api-endpoints.js` — CLI dựng middleware `/http`, nhận `{url, method, headers, body}` rồi gọi `fetch` **bằng Node trên máy mình**. Không kiểm tra scheme, không kiểm tra domain. Vì vậy `127.0.0.1` trỏ về loopback của máy dev, nơi `server/` và `mock-openAPI/` đang chạy.

Hai hệ quả:

1. **CORS bị bỏ qua hoàn toàn ở dev.** Request đi từ Node chứ không từ trình duyệt. Đừng tưởng backend không cần CORS — lên thiết bị thật là lộ ra.
2. **Không được hardcode URL backend.** Đổi `VITE_API_BASE` sang HTTPS là xong, nếu mọi lời gọi đều đi qua `src/api/client.ts`.

---

## 3. Đăng nhập và người dùng ẩn danh

> **[Tài liệu]** Quy chế §2.4.2 — nếu người dùng từ chối uỷ quyền, phải có chế độ ẩn danh.
>
> §3.4.8 — "Mini App phải hoạt động bình thường đối với người dùng **không định danh**."
>
> `/framework/performance/lcp` — "Hạn chế Consent ở trang đầu tiên... quá trình lấy auth code + exchange token sau đó mới gọi API để hiển thị App cũng sẽ làm điểm LCP và trải nghiệm người dùng không tốt."

**Buộc sửa thiết kế hiện tại.** Ngày 1 đang là đăng nhập trước rồi mới vào. Phải đổi thành:

| Việc | Cần đăng nhập |
|---|---|
| Duyệt shop, xem sản phẩm, tìm kiếm, thêm giỏ | **không** |
| Thanh toán, đơn hàng, mở shop | có |

Backend đã hợp: `GET /shops/{id}` vốn công khai. Chỉ luồng frontend phải theo.

Các quy định khác cùng mục: §2.4.1 phải cho đăng nhập bằng V-ID; §2.4.3 phải đăng ký được ngay trong app; §2.4.5 giữ phiên đăng nhập càng lâu càng tốt.

### `getAuthCode` — chữ ký thật

**[Code]** `@v-miniapp/apis/dist/types/api/get-auth-code.d.ts`:

```ts
type IVsfGetAuthCodeAuthScope = 'profile' | 'phone' | 'email'   // KHÔNG có 'auth'
type IVsfGetAuthCodeData = {
  authCode: string
  authSuccessScopes: IVsfGetAuthCodeAuthScope[]
  authErrorScopes?: Record<IVsfGetAuthCodeAuthScope, string>
}
```

Vẫn thiếu scope `auth` như đã ghi ở [docs/day1/login.md](../day1/login.md) §6 — SDK đi sau tài liệu.

`getUserInfo()` trả `{ name, avatar?, gender?, dateOfBirth? }` — **không có định danh, không có token**. Chỉ dùng để vẽ giao diện, tuyệt đối không được coi là danh tính.

---

## 4. Thanh toán

### Quy chế cấm mô hình sàn thông thường

> **[Tài liệu]** Quy chế §5.1.1 — "**Bắt buộc sử dụng các phương thức thanh toán sẵn có của Nền tảng**"
>
> §5.1.2 — "Nghiêm cấm sử dụng các phương thức thanh toán không thuộc hệ sinh thái Nền tảng: Tiền mặt (COD), Chuyển khoản ngân hàng trực tiếp, Quét mã QR cá nhân, Tài sản số"

**COD bị cấm.** Chuyển khoản thẳng cho người bán cũng cấm. Tiền phải chảy qua nền tảng, nghĩa là V-Market là **merchant of record** và phải tự làm phần chia tiền cho người bán.

Khớp với thứ đã tìm được từ trước: `sellerMerchantId` có tồn tại nhưng **không** chia tiền.

§5.2.1: mọi phụ phí (vận chuyển, dịch vụ, thuế) phải hiện đầy đủ **trước** khi người dùng xác nhận. Giỏ nhiều người bán thì phí từng shop phải tách rõ.

### Không chạy được nếu chưa đăng ký app

**[Code]** `initPayment` bắt buộc `paymentApiKey` và `orderInfo.secureHash`. `paymentApiKey` lấy từ app đã đăng ký, không có thì là chuỗi rỗng.

> **[Tài liệu]** `/development/testing/simulate-payment` — Payment Simulator "tích hợp sẵn trong nền tảng **DevAssistant**".

Mà DevAssistant đòi app đã đăng ký và đã upload build. Nên **thanh toán phải mock hoàn toàn**.

> "Vì luồng giả lập **không thể tạo được giá trị `secureHash`** nên nếu user muốn dùng IPN để update order status thì cần **bỏ phần validate `secureHash`** khi test"

**[Suy luận]** Phần verify chữ ký ở IPN phải nằm sau một cờ cấu hình ngay từ đầu. Viết cứng đường tắt là cách một mẹo test lọt ra production.

`secureHash` phải tính ở `server/`. Tính ở frontend đồng nghĩa với việc gửi khoá bí mật xuống máy người dùng.

---

## 5. Điều hướng và màn hình

> **[Tài liệu]** Quy chế §3.1.2 — điều hướng **không quá 5 màn**. §3.1.3 — bottom bar **tối đa 5 tab**.

Chuỗi tự nhiên Home → Danh mục → Shop → Sản phẩm → Giỏ → Thanh toán đã là **6**. Phải làm phẳng có chủ đích: vào thẳng sản phẩm từ trang chủ hoặc tìm kiếm, coi shop là bộ lọc chứ không phải một tầng bắt buộc.

Cộng với ràng buộc kỹ thuật đã biết: đường dẫn **chỉ một tầng**, chi tiết dùng query param (`/product?id=123`).

> **[Tài liệu]** `/framework/deeplink` — "Page được khai báo có phân biệt chữ hoa / thường. `/getauthcode` hay `/GetAuthCode` sẽ mở **trang chủ** vì chưa được khai báo trong router."

Route **phân biệt hoa thường**, và path không khớp thì **âm thầm về trang chủ** thay vì báo lỗi. Đặt tên toàn chữ thường và thêm một route bắt-tất, nếu không link hỏng sẽ bị che mất.

> `/framework/performance/optimize` — "Bạn nên sử dụng Router của Mini App Component thay vì React Router hay TanStack Router... nên dùng **browser mode** để hỗ trợ swipe back hay bấm nút back trên android."

Quy chế §3.1.4 bắt buộc nút back hoạt động, nên browser mode là bắt buộc chứ không phải khuyến nghị.

Vài quy định giao diện khác: §3.2.2 không được có màn hình loading toàn trang lúc mở; §3.2.4 xin quyền đúng ngữ cảnh, không xin lúc mở app; §3.3.6 trạng thái rỗng và lỗi không được để trắng.

---

## 6. Hiệu năng — là tiêu chí kiểm duyệt

> **[Tài liệu]** Quy chế §4.2.2 và §4.2.3

| Chỉ số | Ngưỡng |
|---|---|
| LCP trang đầu | < 2.5s |
| LCP trang sau | < 1.5s |
| Chuyển trang | < 500ms |
| **Phản hồi server** | **< 1s** |

Ngưỡng < 1s áp cho `server/` của mình. API danh sách sản phẩm nhiều người bán phải có index và cache mới đạt.

Cách tính LCP **khác Google Web Vitals** vì có màn hình Consent. Hai luật dễ dính:

> "Nếu phần tử nội dung lớn nhất bị xoá khỏi khung nhìn hoặc khỏi DOM, thì phần tử đó **vẫn là** phần tử nội dung lớn nhất."
>
> "Mini App sẽ **ngừng theo dõi** các phần tử mới ngay khi người dùng tương tác với trang."

**[Suy luận]** Khối skeleton to hơn nội dung thật sẽ bị chốt làm LCP. Giữ skeleton **bằng hoặc nhỏ hơn** phần nó thay thế.

Quy tắc dựng danh sách:

- Danh sách dài phải **virtual scroll** — tài liệu gọi tên `react-window` hoặc `react-virtuoso`, và ví dụ của nó chính là danh sách sản phẩm
- Ảnh: `loading="lazy"`, nén, WebP/AVIF, qua CDN
- Font mặc định **Inter**, đổi font là tốn thêm lượt tải
- Không cài thư viện chỉ để dùng một hàm

**Lưu ý domain CDN ảnh cũng phải whitelist**, mà whitelist bind vào build — nên phải chốt CDN trước bản build đầu tiên định thử trên máy thật.

---

## 7. Lưu trữ

> **[Tài liệu]** `/framework/performance/optimize` — "Trong tương lai, MiniApp cũng sẽ có kế hoạch **ngừng hỗ trợ localStorage, cookie**."

Dùng storage JSAPI ngay từ đầu: `setStorage`, `getStorage`, `removeStorage`, `clearStorage`, `getStorageInfo`.

`getStorageInfo()` trả `{ keys, currentSize, limitSize }` — **có hạn mức thật**. Không cache toàn bộ danh mục sản phẩm ở client.

Token phiên và giỏ hàng chính là thứ hay bị nhét vào `localStorage` — bọc qua JSAPI từ commit đầu.

---

## 8. Dữ liệu cá nhân và người bán

> **[Tài liệu]** Quy chế §7.1.5 — "Nghiêm cấm Nhà phát triển chia sẻ dữ liệu người dùng với bên thứ 3 khi chưa có sự đồng ý... **Bên thứ 3 được hiểu là các tổ chức/cá nhân không phải là VSF.**"

**Người bán của mình là bên thứ ba.** Định nghĩa "chia sẻ" rất rộng, gồm cả "truy cập vào hệ thống để xem/sử dụng dữ liệu" — tức là người bán đăng nhập vào trang quản lý để xem đơn cũng tính.

Đưa tên, số điện thoại, địa chỉ người mua cho người bán để giao hàng cần bước đồng ý riêng, nói rõ dữ liệu sẽ tới người bán.

Cơ chế đồng ý (§7.1.3): phải là **checkbox, không được tick sẵn**. §7.1.11: cần một màn hình riêng để người dùng cấp và rút đồng ý theo từng mục đích. §7.1.9: rút là dừng thu thập ngay — ghép với sự kiện `onSettingsChanged`.

Trách nhiệm (§6.1.3.3): nhà phát triển **chịu trách nhiệm hoàn toàn** với tranh chấp sau bán, gồm cả hoàn tiền và bồi thường. Cộng với §6.2.1 đòi hotline hoặc hệ thống chăm sóc khách hàng, và SLA phản hồi ≤ 72 giờ (≤ 24 giờ nếu nền tảng chuyển sang).

---

## 9. Vòng đời trang

**[Tài liệu]** `/framework/h5-app/lifecycle` — với app H5 đây là **sự kiện DOM trên `window`**, không phải hook React:

| Sự kiện | Khi nào |
|---|---|
| `onAppResume` | app hiện trở lại |
| `onAppPause` | app bị che |
| `onCustomIconEvent` | chạm icon tự thêm trên nav bar |
| `onSettingsChanged` | người dùng đổi quyền riêng tư |

```js
window.addEventListener('onAppResume', handler)   // dữ liệu ở (evt as CustomEvent).detail
```

Bộ `onLoad / onReady / onShow / onHide / onUnload` thuộc về **MiniApp DSL**, không dùng được cho H5. DSL đang "Comming soon" — ta làm H5.

---

## 10. Chỗ tài liệu sai

Đã kiểm chứng bằng type trong package. Đi theo tài liệu ở những chỗ này sẽ ra code không chạy.

| Tài liệu nói | Thực tế |
|---|---|
| `<Icon name="home" />` | **không có** icon `home`, tên đúng là `house` |
| `<Icon name="home-outline" />` | sai type — `IIconName` đã cắt hậu tố. Đúng: `<Icon name="house" type="fill" />` |
| `showPaymentMethod()` không tham số | bắt buộc `{ paymentApiKey }` |
| `openNativeAppStore` | tên export là **`openNativeStore`** |
| Cổng dev "typically" 3000–3999 / 8080–8999 | cố định đúng như vậy trong code |
| `NumberField` cho "Amount" | `ai-guidelines` ghi **chỉ dùng cho OTP/PIN**; số lượng và giá dùng `TextField type="number"` |
| `transparentTitle` có 3 giá trị (`none`/`always`/`auto`) | trang `custom-header` chỉ ghi 2. **[Suy luận]** `auto` là mới, cần thử trước khi tin |

Bộ icon có **123 tên gốc**, và **không có** icon nào cho giỏ hàng hay cửa hàng (`cart`, `bag`, `basket`, `shop`, `store`, `box`, `truck` đều không có). Đây là bộ icon cho hệ sinh thái Vingroup — xe điện, trạm sạc, chuyến bay. Bottom tab của V-Market phải chọn tên gần đúng hoặc truyền ReactNode tự vẽ, vì `items[].icon` nhận `IIconProps | ReactNode`.

Skill mô tả 10 nhóm component, nhưng `dist/components/` có 43 thư mục. Những cái **có thật mà tài liệu không nhắc**, và đều cần cho danh sách sản phẩm:

| Component | Props |
|---|---|
| `Image` | `lazy`, `fit`, `placeholder`, `fallback` |
| `ListItem` | `label`, `description`, `prefix`, `suffix`, `leadContent`, `trailContent`, `divider` |
| `PullToRefresh` | `onRefresh`, `threshold`, `renderText(status)` |
| `Skeleton` | + `SkeletonTitle`, `SkeletonParagraph` |
| `Pagination` | |

**Quy tắc rút ra: khi cần một component mà skill không nhắc tới, tra thẳng `.d.ts` trong `node_modules` — chắc chắn hơn tài liệu.**

---

## 11. Việc đang chặn

Xếp theo mức độ chặn.

| | Việc | Ai làm được |
|---|---|---|
| 1 | **Đăng ký app ở DevCenter** — mở khoá `appIdentifier` thật, test trên máy thật, thanh toán, whitelist domain. Danh mục ứng dụng **chọn xong không đổi được**. | chỉ bạn |
| 2 | **Xác nhận mô hình thanh toán** — COD bị cấm, ảnh hưởng Proposal | chỉ bạn |
| 3 | Backend HTTPS công khai + whitelist, để test trên máy thật | sau (1) |
| 4 | DPA với bộ phận Legal/DPO của VSF nếu bên làm không thuộc VSF | chỉ bạn |

Chưa có (1) thì vẫn làm được: toàn bộ giao diện, luồng đăng nhập giả qua `mock-openAPI`, và mọi thứ phía sau `authCode` — vì phần đó giống hệt nhau ở cả hai chế độ.
