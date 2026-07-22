# Ràng buộc của nền tảng V-App

Đọc từ `developer.v-app.vn`, hai skill trong `.claude/skills/`, và code trong `node_modules/@v-miniapp/`.

Phần 1 là những thứ **đổi cách mình làm** — nên đọc. Phần 2 là thứ ngoài tầm. Phần 3 để **tra khi cần**, không cần đọc bây giờ.

Chỗ nào tài liệu và code mâu thuẫn thì tin code, và ghi rõ ở §10.

---

# Phần 1 — Bốn thứ đổi cách làm

## 1. Trong V-App không có `fetch`

Viết web bình thường, muốn gọi API thì `fetch('/api/shops')`. Trình duyệt nào cũng có hàm đó.

MiniApp thì không. Nó chạy trong một hộp JavaScript bị cắt bớt, và V-App **đã gỡ `fetch` ra khỏi hộp**:

> "Ứng dụng của bạn sẽ được chạy trong môi trường cô lập thuần javascript nên sẽ không có các hàm gọi network thông thường như `fetch` hay `XMLHttpRequest`."
> — `/api/network/request`

Phải gọi qua cầu nối của họ:

```ts
await apisAsync.request({ url, method: 'GET', dataType: 'JSON', timeout: 30000 })
```

**Vì sao họ làm vậy:** để mọi request đi qua tay họ, nhờ đó chặn được domain lạ và ép HTTPS.

**Kéo theo:** axios không dùng được. Thư viện nào giả định có `fetch` cũng vậy. TanStack Query thì được, vì nó không gắn với cách gọi mạng — chỉ cần tự viết `queryFn`.

**Việc phải làm:** đúng một file là nơi duy nhất chọn URL và cách gọi.

```ts
// src/api/client.ts
const BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:4000'

export async function apiRequest<T>(path: string, init = {}): Promise<T> {
  const res = await apisAsync.request({ url: `${BASE}${path}`, dataType: 'JSON', ...init })
  return res.data as T
}
```

Không phải cho đẹp. Rải `apisAsync.request` khắp nơi thì hôm đổi địa chỉ backend phải sửa vài chục chỗ.

### Hai cái bẫy đi kèm

**CORS không bao giờ báo lỗi ở dev.** Trong Simulator, request không đi từ trình duyệt mà vòng qua một tiến trình Node chạy trên máy bạn (`@v-miniapp/cli/dist/plugins/api-endpoints.js`, middleware `/http`). Node gọi hộ, nên `127.0.0.1:4000` chạy được và CORS không bị kiểm tra. Đừng vì thế mà tưởng backend không cần CORS.

**`apisAsync` chết ngoài V-App.** Cầu nối là `new Proxy({}, { get(_, o) { return window.vsf[o] } })` — đọc `window.vsf` **không kiểm tra tồn tại**. Mở trong tab trình duyệt thường, chạy unit test, hay Storybook đều nhận `TypeError`. Muốn test được thì phải bọc một lớp kiểm tra `typeof window !== 'undefined' && window.vsf`.

---

## 2. Chưa đăng nhập vẫn phải xem được hàng

> "Mini App phải hoạt động bình thường đối với người dùng **không định danh**." — Quy chế §3.4.8
>
> Nếu người dùng từ chối uỷ quyền, phải có chế độ ẩn danh. — §2.4.2

Hợp lý thôi: mở Shopee đâu có bị bắt đăng nhập trước khi xem hàng.

Hướng dẫn hiệu năng nói cùng một điều, vì lý do khác:

> "Hạn chế Consent ở trang đầu tiên... quá trình lấy auth code + exchange token sau đó mới gọi API để hiển thị App cũng sẽ làm điểm LCP và trải nghiệm người dùng không tốt."
> — `/framework/performance/lcp`

**Thiết kế ngày 1 đang làm ngược** — vào là đăng nhập, xong mới thấy gì. Phải đổi:

| Việc | Cần đăng nhập |
|---|---|
| Duyệt shop, xem sản phẩm, tìm kiếm, thêm giỏ | **không** |
| Thanh toán, xem đơn, mở shop | có |

Backend đã đúng sẵn: `GET /shops/{id}` vốn công khai. Chỉ luồng màn hình phải sửa.

---

## 3. Đường dẫn phẳng, và không quá 5 tầng

Hai ràng buộc riêng biệt, cùng đẩy về một hướng.

**Kỹ thuật** — router chỉ nhận một tầng:

> Supported: `/home`, `/settings`, `/products`
> Not supported: `/products/detail`, `/users/:id`, `/category/:slug`
> — skill `ai-guidelines/app.md`, đánh dấu CRITICAL

Chi tiết phải dùng query param: `navigate('/product', { params: { id } })` → `/product?id=123`, đọc bằng `useLocation()?.params?.id`.

**Kiểm duyệt** — §3.1.2: điều hướng không quá 5 màn. §3.1.3: bottom bar tối đa 5 tab.

Chuỗi tự nhiên của một sàn là Trang chủ → Danh mục → Shop → Sản phẩm → Giỏ → Thanh toán. **Đã 6.**

Nên phải cố tình làm phẳng: từ trang chủ bấm thẳng vào sản phẩm, coi shop là **bộ lọc** chứ không phải chặng bắt buộc đi qua.

Bản đồ màn hình:

| Đường dẫn | |
|---|---|
| `/` | Danh sách shop / sản phẩm |
| `/shop?id=` | Chi tiết shop |
| `/product?id=` | Chi tiết sản phẩm |
| `/cart` | Giỏ |
| `/checkout` | Thanh toán |
| `/orders`, `/order?id=` | Đơn hàng |
| `/seller` | Shop của tôi |

**Một cái bẫy:** route phân biệt hoa thường, và path không khớp thì **âm thầm về trang chủ** thay vì báo lỗi (`/framework/deeplink`). Đặt tên toàn chữ thường, và thêm một route bắt-tất, nếu không link hỏng sẽ bị che mất.

Và dùng Router của thư viện, **không dùng React Router** — ở chế độ browser mode, để nút back Android và vuốt back iOS hoạt động (quy chế §3.1.4 bắt buộc).

---

## 4. COD bị cấm

Không phải chuyện code, mà là chuyện mô hình.

> "5.1.1 **Bắt buộc sử dụng các phương thức thanh toán sẵn có của Nền tảng**
> 5.1.2 Nghiêm cấm... Tiền mặt (COD), Chuyển khoản ngân hàng trực tiếp, Quét mã QR cá nhân"

V-Market **không thể** là cái chợ chỉ ghép người mua với người bán rồi để họ tự trả tiền nhau. Tiền phải chảy qua cổng của V-App, nghĩa là V-Market **đứng tên thu tiền** rồi tự chia lại cho người bán.

Đúng bằng phát hiện cũ: `sellerMerchantId` có tồn tại nhưng **không** chia tiền. Hai nguồn độc lập cùng chỉ về một kết luận.

Kèm §5.2.1: mọi phụ phí phải hiện đầy đủ **trước** khi xác nhận. Giỏ nhiều shop thì phí từng shop phải tách rõ.

### Người bán là "bên thứ ba"

> "Nghiêm cấm... chia sẻ dữ liệu người dùng với bên thứ 3 khi chưa có sự đồng ý... **Bên thứ 3 được hiểu là các tổ chức/cá nhân không phải là VSF.**" — §7.1.5

Người bán của mình **không phải VSF**, nên là bên thứ ba. Định nghĩa "chia sẻ" rộng tới mức gồm cả *"truy cập vào hệ thống để xem dữ liệu"* — tức người bán mở trang quản lý xem đơn cũng tính.

Đưa tên, số điện thoại, địa chỉ người mua cho người bán để giao hàng cần một bước đồng ý riêng, nói rõ dữ liệu sẽ tới người bán. Checkbox, **không được tick sẵn** (§7.1.3).

---

# Phần 2 — Cái gì ngoài tầm, và thay bằng gì

Không có quyền truy cập DevCenter. Đây là **tiền đề của dự án**, không phải việc tồn đọng chờ làm — nó là lý do `mock-openAPI/` tồn tại từ ngày 1.

| Cái không có | Kéo theo mất | Thay bằng |
|---|---|---|
| `appIdentifier` đã đăng ký | `getAuthCode` thật, `deploy` | `/simulator/authcode` của mock |
| `client_id` / `client_secret` | đổi authCode lấy token | `/oauth2/token/exchange` của mock |
| `paymentApiKey` | `initPayment`, `showPaymentMethod` | trang thanh toán giả + IPN tự gửi |
| DevAssistant | test máy thật, Payment Simulator, đo LCP thật | Simulator của CLI |
| Whitelist domain | gọi backend từ máy thật | proxy Node của `dev`, trỏ `127.0.0.1:4000` |

Vì vậy **cả ứng dụng chỉ chạy trong Simulator của `v-miniapp-cli dev`**. Mọi quyết định thiết kế nhắm vào đó.

**Điều đó không làm giảm giá trị phần đã làm.** Mọi thứ phía sau `authCode` giống hệt nhau ở cả hai chế độ: đổi token, gọi userinfo, tạo user, cấp JWT, phân quyền, shop, đơn hàng. Ranh giới mock nằm đúng một chỗ — `VAPP_BASE_URL` — và `test_contract.py` chạy được với cả API thật để chứng minh bản mock bám đúng hợp đồng.

**Vẫn phải ghi nhận** các ràng buộc ở §2, §3, §4: không kiểm chứng được bằng cách chạy thử vì không qua kiểm duyệt, nhưng chúng quyết định sản phẩm này có triển khai thật được hay không.

---

# Phần 3 — Tra khi cần

## 5. Hiệu năng — là tiêu chí kiểm duyệt

| Chỉ số | Ngưỡng |
|---|---|
| LCP trang đầu | < 2.5s |
| LCP trang sau | < 1.5s |
| Chuyển trang | < 500ms |
| **Phản hồi server** | **< 1s** |

Ngưỡng < 1s áp cho `server/` của mình.

Cách tính LCP khác Google Web Vitals vì có màn hình Consent. Hai luật dễ dính:

- Phần tử lớn nhất bị xoá khỏi DOM thì **vẫn** được tính là phần tử lớn nhất
- **Ngừng đo ngay khi người dùng chạm vào màn hình**

*(Suy luận)* Khối skeleton to hơn nội dung thật sẽ bị chốt làm LCP. Giữ skeleton **bằng hoặc nhỏ hơn** phần nó thay thế.

Dựng danh sách: phải **virtual scroll** — tài liệu gọi tên `react-window` hoặc `react-virtuoso`, ví dụ của nó chính là danh sách sản phẩm. Ảnh `loading="lazy"`, nén, WebP/AVIF, qua CDN. Font mặc định **Inter**, đổi font tốn thêm lượt tải.

**Domain CDN ảnh cũng phải whitelist**, mà whitelist bind vào bản build — nên phải chốt CDN trước bản build đầu tiên định thử trên máy thật.

## 6. Lưu trữ

> "Trong tương lai, MiniApp cũng sẽ có kế hoạch **ngừng hỗ trợ localStorage, cookie**."

Dùng storage JSAPI từ đầu: `setStorage`, `getStorage`, `removeStorage`, `clearStorage`, `getStorageInfo`.

`getStorageInfo()` trả `{ keys, currentSize, limitSize }` — **có hạn mức thật**, đừng cache cả danh mục.

Token phiên và giỏ hàng chính là thứ hay bị nhét vào `localStorage`. Bọc qua JSAPI ngay.

## 7. Vòng đời trang

Với app H5 đây là **sự kiện DOM trên `window`**, không phải hook React:

| Sự kiện | Khi nào |
|---|---|
| `onAppResume` | app hiện trở lại |
| `onAppPause` | app bị che |
| `onCustomIconEvent` | chạm icon tự thêm trên nav bar |
| `onSettingsChanged` | người dùng đổi quyền riêng tư |

```js
window.addEventListener('onAppResume', handler)   // dữ liệu ở (evt as CustomEvent).detail
```

Bộ `onLoad / onReady / onShow / onHide / onUnload` thuộc **MiniApp DSL** — DSL đang "Comming soon", ta làm H5, không dùng được.

## 8. `app-config.json`

```json
{
  "appIdentifier": "...",
  "appName": "...",
  "h5App": "YES",
  "window": { "defaultTitle": "", "transparentTitle": "always" }
}
```

`h5App: "YES"` bắt buộc, không có thì nó render MiniApp DSL.

`defaultTitle: ""` + `transparentTitle: "always"` phải giữ nguyên với app dùng `ui-react` — nếu không sẽ có **hai** thanh tiêu đề chồng nhau, một của hệ thống một của thư viện.

Trang cấu hình có nhắc `tabBar` nhưng không mô tả — **trang được khai báo ở `src/app.config.ts`**, không phải ở đây.

## 9. Whitelist domain

> "Bất kỳ request nào gửi đến các tên miền không nằm trong danh sách an toàn này đều sẽ **bị nền tảng chặn tự động**."
> — `/development/devcenter/whitelist-domain`

| `127.0.0.1:4000` | |
|---|---|
| `v-miniapp-cli dev` | ✅ chạy (proxy Node trên máy mình) |
| Máy thật / production | ❌ chết |

### Cách mở một domain

Bốn bước, làm trong V-Console bằng tài khoản **Admin** của Mini App:

| | |
|---|---|
| 1 | Cài đặt → **Quản lý tên miền** → **Tạo tên miền** |
| 2 | Nhập domain kèm giao thức (`https://` hoặc `wss://`), bấm **Tải tệp xác thực** → nhận `vsf-verification.txt` |
| 3 | Đặt tệp đó vào **thư mục gốc** của server, mở được công khai tại `https://domain/vsf-verification.txt` |
| 4 | Quay lại V-Console bấm **Thêm tên miền** — backend của VSF tự gọi vào đọc tệp để xác minh |

Whitelist **bind vào bản build**: domain thêm sau chỉ áp dụng cho build upload sau đó. Build cũ không tự nhận danh sách mới, phải build lại và upload lại.

Năm lỗi tài liệu liệt kê, đáng để ý ba cái sau vì không rõ ràng:

- **SSL tự ký bị từ chối.** Phải là chứng chỉ do một CA uy tín cấp.
- **Không được redirect.** Khai `https://domain.com` mà server tự chuyển sang `https://www.domain.com` là hỏng — backend không đi theo redirect.
- **Cloudflare / firewall chặn.** Request kiểm tra của VSF phải đọc được tệp đó; nếu proxy chặn bot thì phải mở ngoại lệ riêng cho đường dẫn này.

### Hệ quả lớn: chỉ whitelist được domain mình sở hữu

Bước 3 đòi **đặt tệp vào thư mục gốc** của domain. Nghĩa là không sở hữu domain thì không whitelist được.

Nên các domain bên thứ ba **không dùng được**, kể cả khi chúng phổ biến:

| | |
|---|---|
| `fonts.gstatic.com` | không đặt tệp lên máy chủ Google được |
| CDN ảnh của bên khác (Cloudinary, imgix…) | trừ khi mua domain riêng trỏ về |
| API bản đồ, reverse geocoding | phải proxy qua backend của mình |

**Cách duy nhất là proxy qua backend của mình.** Ảnh, font, dịch vụ ngoài — tất cả đi qua domain đã whitelist, backend gọi ra ngoài rồi trả về. Điều này cũng khớp với mục §6 hiệu năng: CDN ảnh phải là domain của mình.

### Về font Inter

Thư viện nhúng **15 khối `@font-face`** trỏ tới `https://fonts.gstatic.com`. Mà theo trên thì domain đó **không whitelist được**.

*(Suy luận)* Nhiều khả năng V-App đã có sẵn Inter trong ứng dụng chủ, nên `@font-face` không bao giờ phải tải — câu *"ưu tiên dùng Inter giống V-App để tránh việc tải lại Font"* trong tài liệu hiệu năng chính là ý đó. Nếu vậy thì không có vấn đề gì.

Không phân biệt được hai khả năng từ máy dev: Simulator có internet nên trường hợp nào cũng chạy. Chỉ lộ ra trên thiết bị thật, và nếu sai thì chữ rơi về `sans-serif` của hệ điều hành chứ không vỡ layout.

Kết luận thực dụng: **đừng đổi font**, và đừng tự thêm `@font-face` trỏ ra ngoài — cái đó thì chắc chắn hỏng.

## 10. Chỗ tài liệu sai

Đã kiểm bằng type trong package. Đi theo tài liệu ở những chỗ này sẽ ra code không chạy.

| Tài liệu nói | Thực tế |
|---|---|
| `<Icon name="home" />` | **không có** icon `home`, tên đúng là `house` |
| `<Icon name="home-outline" />` | sai type — `IIconName` đã cắt hậu tố. Đúng: `<Icon name="house" type="fill" />` |
| `showPaymentMethod()` không tham số | bắt buộc `{ paymentApiKey }` |
| `openNativeAppStore` | tên export là **`openNativeStore`** |
| `NumberField` cho "Amount" | `ai-guidelines` ghi **chỉ dùng cho OTP/PIN**; số lượng và giá dùng `TextField type="number"` |
| `transparentTitle` có 3 giá trị | trang `custom-header` chỉ ghi 2. *(Suy luận)* `auto` là mới, thử trước khi tin |

**Bộ icon có 123 tên, và không có cái nào cho giỏ hàng hay cửa hàng** — `cart`, `bag`, `basket`, `shop`, `store`, `box`, `truck` đều không có. Đây là bộ icon cho hệ sinh thái Vingroup: xe điện, trạm sạc, chuyến bay. Bottom tab phải chọn tên gần đúng hoặc tự vẽ — `items[].icon` nhận `IIconProps | ReactNode` nên có đường thoát.

**Skill mô tả 10 nhóm component, `dist/components/` có 43 thư mục.** Những cái có thật mà tài liệu không nhắc, đều cần cho danh sách sản phẩm:

| Component | Props |
|---|---|
| `Image` | `lazy`, `fit`, `placeholder`, `fallback` |
| `ListItem` | `label`, `description`, `prefix`, `suffix`, `leadContent`, `trailContent` |
| `PullToRefresh` | `onRefresh`, `threshold`, `renderText(status)` |
| `Skeleton` | + `SkeletonTitle`, `SkeletonParagraph` |
| `Pagination` | |

**Quy tắc:** cần component mà skill không nhắc tới thì tra thẳng `.d.ts` trong `node_modules` — chắc hơn tài liệu.

### Ba thứ tài liệu không nói, tự mò ra khi chạy

**Dev server chỉ bind IPv6.** `http://127.0.0.1:8080` → không kết nối được. `http://localhost:8080` → 200. Lỗi trông y hệt như server chưa chạy, nên dễ mất thời gian.

**Payload của proxy lồng hai tầng, và `payload.method` không phải HTTP method** mà là loại thao tác (`upload` / `download` / còn lại). HTTP method nằm trong `params`:

```json
{"id":"...","payload":{"method":"request","params":{"url":"...","method":"GET"}}}
```

Đọc ra từ `@v-miniapp/cli/dist/plugins/api-endpoints.js`. Bình thường không cần biết vì `apisAsync.request` lo hộ — chỉ cần khi muốn gọi thẳng vào proxy để kiểm tra.

**`tsconfig` của template bật `erasableSyntaxOnly`.** Không dùng được cú pháp gán thuộc tính ngay trong tham số constructor (`constructor(readonly x: number)`), phải khai báo trường tách ra rồi gán trong thân hàm.

## 11. Vài quy định giao diện lặt vặt

- §3.2.2 — không được có màn hình loading toàn trang lúc mở app
- §3.2.4 — xin quyền đúng ngữ cảnh, không xin lúc vừa mở
- §3.3.1 — định dạng số Việt: `3.000.000` và `6,7%`, **dấu ngược với tiếng Anh**
- §3.3.6 — trạng thái rỗng và lỗi không được để trắng
- §3.4.1 — cỡ chữ nền 16px
- §6.2.1 — app có thanh toán thì phải có hotline hoặc kênh chăm sóc khách hàng
