# Frontend V-Market — kiến trúc MiniApp

Tài liệu này giải thích code trong `v-market/src`: màn hình nào, dữ liệu chảy thế nào, và những chỗ phải lách thư viện.

---

## 1. Bản đồ màn hình

```mermaid
flowchart LR
    subgraph tabs["4 tab gốc — không có nút back"]
        HOME["/  Trang chủ"]
        CART["/cart  Giỏ hàng 🛒(n)"]
        ORDERS["/orders  Đơn hàng"]
        ACCOUNT["/account  Tài khoản"]
    end

    HOME -- "chạm thẻ (kèm state)" --> PRODUCT["/product?id=…\nChi tiết sản phẩm"]
    PRODUCT -- "Mua ngay" --> CART
    ACCOUNT -- "khách" --> LOGIN["/login\nChọn tài khoản V-App"]
    LOGIN -- "AUTHENTICATED" --> ACCOUNT
```

Luật route (từ [platform-constraints.md](platform-constraints.md) §3):

- **Một tầng, chữ thường** — chi tiết dùng query (`/product?id=…`), không có `/product/123`
- Path chưa đăng ký → **âm thầm về trang chủ**, nên tab hỏng trông như tab chạy
- **Nút back**: một component ở `Layouts` cấp app bọc mọi trang, tự ẩn ở 4 tab gốc — trang mới sinh ra sau tự có back, không ai phải nhớ
- **Tab bar tự ẩn** ở trang không có `bottomTabBarId` (`/product`, `/login`) — nhường chỗ cho thanh Mua ngay
- Tab đang đứng nổi lên: `activeColor` teal + `activeIcon` bản fill + nâng nhẹ

## 2. Các tầng

```
pages/            màn hình — giữ state của màn đó
components/       khối giao diện dùng lại (promo, flash sale, lưới, back button…)
lib/              cart.ts · auth.ts · storage.ts · format.ts — store và tiện ích
api/              auth.ts · products.ts · shops.ts — gọi backend/mock, có type
api/client.ts     CHỐT CHẶN duy nhất chọn transport
```

### `client.ts` — luật chọn đường

| URL | Đi đường nào | Vì sao |
|---|---|---|
| `https://…` + có bridge | `apisAsync.request` | máy thật: **không có `fetch`**, bridge chỉ nhận https |
| `http://…` (dev) | `fetch` của trình duyệt | bridge từ chối http ngay phía client; Simulator là trình duyệt thật nên fetch tồn tại — đổi lại `server/` và `mock-openAPI/` phải bật CORS cho origin localhost |
| bắt đầu bằng `http` | dùng nguyên | luồng auth gọi mock ở base riêng (`VITE_VAPP_BASE`) |

Chuyển sang máy thật = đổi **một dòng `.env`** sang https, không đổi code.

### Store là module, không phải Context

`Layouts` của router bọc **từng trang một** — đặt Provider ở đó là mỗi trang một bản state riêng. Nên `cart.ts` và `auth.ts` là module singleton + `useSyncExternalStore`: một state, mọi trang nhìn chung, component nào cũng subscribe được (kể cả icon tab nằm trong config tĩnh).

### `storage.ts` — seam lưu trữ

Trong V-App đi storage JSAPI (nền tảng sẽ bỏ `localStorage`/cookie), ngoài V-App rơi về `localStorage`. Hỏng thì trả `null`, không sập màn hình. Giỏ (`cart.v1`) và phiên (`session.v1`) đều đi qua đây.

## 3. Đăng nhập — consent hai giai đoạn thành hình

```mermaid
sequenceDiagram
    autonumber
    participant UI as /login
    participant VA as mock-openAPI<br/>(vai V-App)
    participant BE as server/

    UI->>VA: POST /simulator/authcode {scopes:"auth"}
    VA-->>UI: authCode
    UI->>BE: POST /auth/session {authCode}
    alt tài khoản đã biết
        BE-->>UI: AUTHENTICATED + JWT → vào thẳng, không hỏi gì
    else tài khoản mới
        BE-->>UI: CONSENT_REQUIRED
        Note over UI: Sheet "V-App chia sẻ thông tin"<br/>họ tên · SĐT (để giao hàng)
        UI->>VA: POST /simulator/authcode {scopes:"profile phone"}
        VA-->>UI: authCode mới
        UI->>BE: POST /auth/session
        BE-->>UI: AUTHENTICATED + JWT
    end
```

- Consent hiện **đúng một lần trong đời** mỗi tài khoản — tạo tài khoản mới ở `/login` là cách xem nó
- Từ chối consent → ở lại làm khách, duyệt hàng bình thường (quy chế §3.4.8)
- Client **chỉ cầm JWT của V-Market** — access token của V-App không bao giờ rời server
- **Seam mock↔thật nằm trọn trong `api/auth.ts`**: chỉ chỗ lấy authCode là swappable (thật = `apisAsync.getAuthCode`, cần app đăng ký DevCenter — không có). Mọi thứ sau authCode giống hệt nhau ở hai chế độ
- Trên máy thật, cả màn `/login` **không tồn tại** — người dùng đã đăng nhập V-App sẵn, `getAuthCode` chạy im lặng

### Hỏi đăng nhập ở đâu: hai cách, tuỳ loại trang

`SessionGuardLayout` chặn `/orders`, `/checkout`, `/order`, `/seller`. Nhưng
nó **không** đối xử với chúng như nhau:

| Loại trang | Cách hỏi |
|---|---|
| Tab gốc (`/orders`) | Hiện thẳng "Đăng nhập để xem đơn hàng" **tại chỗ** |
| Còn lại | Đẩy sang `/login`, xong quay về |

Đá người ta khỏi **tab vừa bấm** — và mất luôn thanh tab, vì `/login` không có
`bottomTabBarId` — đọc ra như bị văng khỏi app, chứ không phải như được mời
đăng nhập. Ba tab kia cũng biến mất cùng. Với trang người dùng **cố ý mở**
(`/checkout`, `/order`) thì chuyển hướng lại đúng: họ xin trang đó, và sẽ được
trả lại đúng trang đó.

`SignInRequired` cố tình trông giống các empty state bên cạnh nó — chưa đăng
nhập là **trạng thái bình thường**, không phải lỗi.

> Đổi thứ tự `Layouts` thành `[TopChromeLayout, SessionGuardLayout]` vì việc
> này: guard giờ có lúc **thay nội dung trang bằng nội dung của nó**, mà phần
> đó vẫn phải nằm dưới chrome của app. Để guard ở ngoài thì thay trang là mất
> luôn ô tìm kiếm.

`TAB_ROOTS` và `AUTH_REQUIRED` dời về `lib/routes.ts` — trước đó `TAB_ROOTS`
nằm trong `top-chrome-layout.tsx` và giờ cả hai layout đều cần. Lệch nhau thì
triệu chứng rất khó đoán: nút back mọc trên một tab, hoặc một tab bị đá ra.

### Đăng nhập xong thì quay về đâu

Nhánh chuyển hướng đẩy sang `/login` bằng **`replace`** — trang bị chặn chưa
từng mở ra thật, không nên để nút back quay lại.

Nhưng `replace` cũng **xoá luôn nơi người dùng định đến**, và thanh tab cũng
`replace` (`bottom-tab-bar-layout/index.js` gọi `navigate(path, {replace: true})`).
Nên bấm tab **Đơn hàng** lúc chưa đăng nhập là hai lần ghi đè liên tiếp:

```
[/]  ──tab──▶  [/orders]  ──guard──▶  [/login]
```

Không còn gì bên dưới, nên `navigate(-1)` sau khi đăng nhập **không đi đâu
cả** — kẹt lại ở màn đăng nhập. Từ tab Tài khoản thì không dính, vì nút
"Đăng nhập" ở đó là `push` bình thường, còn `[/account]` vẫn nằm dưới.

(Riêng `/orders` giờ không còn đi đường này nữa — nó hỏi tại chỗ. Nhưng cái
bẫy vẫn còn nguyên cho mọi tab gốc cần đăng nhập về sau.)

Cách sửa: guard **mang theo đích đến** trong `state.loginTarget` (cả
`pathname` lẫn `params`, vì `/order?id=` cần id), và `/login` quay về **đúng
tên đường** thay vì lùi lịch sử. Không có `loginTarget` — tức người dùng tự
vào `/login` — thì `navigate(-1)` vẫn là lối ra đúng.

Nút đặt hàng ở giỏ dùng chung cơ chế đó, nên đăng nhập xong là **đi thẳng
sang `/checkout`**, không bắt bấm lại lần nữa.

## 4. Giỏ hàng — nằm ở client

```mermaid
flowchart LR
    P["/product\nThêm giỏ · Mua ngay"] --> S["lib/cart.ts\nmodule store"]
    S <--> ST["storage seam\ncart.v1"]
    S --> C["/cart\ndòng hàng · stepper · tạm tính"]
    S --> B["icon tab 🛒\nbadge số món"]
    C -. "Đặt hàng (bước sau)" .-> BE["server/ kiểm lại\ngiá + kho rồi mới tạo đơn"]
```

Vì sao client: thêm-giỏ phải chạy **không cần đăng nhập**. Giá trong giỏ chỉ là **ảnh chụp để hiển thị** — lúc đặt hàng server kiểm lại giá và kho, client không bao giờ là nguồn sự thật về tiền. Thêm lại món đã có thì làm mới ảnh chụp, giỏ luôn hiện giá người mua vừa nhìn thấy.

Badge trên tab: config app dựng một lần và `IBottomTabBarItem` không có trường badge — nhưng `icon` nhận ReactNode, nên `<CartTabIcon />` là component sống subscribe store từ trong config tĩnh.

## 5. Dữ liệu thật vs demo

| | Nguồn |
|---|---|
| Danh sách sản phẩm, giá, giá sale, quy cách, tên shop | **Postgres** qua `GET /products` (một fetch nuôi cả lưới lẫn dải flash — flash = món có `originalPrice`) |
| Chi tiết sản phẩm | state từ thẻ (mở tức thì) hoặc `GET /products/{id}` khi vào bằng link |
| Đăng nhập, vai trò | **thật** — luồng ngày 1 |
| Mảng demo trong flash/lưới | chỉ còn là **dự phòng** khi backend tắt |
| "Đã bán", "Giao x ngày", "Kho…" | bịa ở thẻ demo — chờ bảng đơn hàng |
| Chữ khuyến mãi banner, nút Đặt hàng | placeholder có chủ đích, ghi rõ trong code |

Gieo lại dữ liệu (test chạy xong là mất): `cd server && .venv\Scripts\python.exe scripts/seed_demo.py`

## 6. Chỗ phải lách thư viện

Chi tiết ở [platform-constraints.md](platform-constraints.md) §10; điểm lại cái đã đụng thật:

| Vấn đề | Cách lách |
|---|---|
| `Image lazy` không bao giờ nạp ảnh trong app này | bỏ `lazy`; ảnh đầu trang eager là đúng LCP |
| `Carousel` mặc định `align:'center'` làm banner lệch trái | `align:'start', gap:0` |
| Toast neo theo navigation bar đã ẩn → bị status bar che | 2 rule CSS neo lại theo `--vsf-title-bar-height` / thanh đáy; toast dùng `position:'bottom'` |
| Cụm `⋯ ✕` của V-App đè lên trang, không chiếm layout | nội dung hàng đầu chừa vùng đó; "Xem tất cả" thuộc hàng Flash sale nằm dưới |
| Bộ icon không có cart/giỏ | emoji ReactNode làm icon tab |

## 7. Form thêm sản phẩm — nút bị khoá phải nói lý do

`ProductFormSheet` khoá nút "Thêm/Lưu" khi form chưa hợp lệ. Bản đầu **khoá
im lặng** — người bán điền xong vẫn thấy nút mờ mà không biết thiếu gì. Hai
nguyên nhân hay gặp, cả hai đều không hiện ra:

- **Giá gõ có dấu phân cách.** VND là số nguyên đồng, người bán gõ `50.000`
  hay `50,000`. `Number("50,000")` ra `NaN` → nút khoá. Giờ `parseVnd` chỉ
  giữ chữ số, nên `50.000`, `50,000`, `50 000`, `50000` đều thành `50000`.
- **Mô tả để trống.** Backend bắt buộc `description` (min_length=1), nên
  client cũng bắt — nhưng trước đây không nói.

Cách sửa đúng: tính `problem` — **yêu cầu chưa đạt đầu tiên, bằng lời** — và
hiện ngay trên nút. Nút disable không bao giờ còn là câu đố. Cùng tinh thần
với thông báo kiểm duyệt ([day13](../day13/security.md) §3): từ chối mà không
nêu lý do là một ticket hỗ trợ đang chờ.

> **Lỗi ô SKU chết:** ô SKU thêm ở phần sau có `useState`, có `TextField`,
> nhưng `save()` **không hề đưa `sku` vào payload** — gõ gì cũng mất. Backend
> vẫn nhận `sku` (`CreateProductRequest`, `UpdateProductRequest`) và có ràng
> buộc `UNIQUE(shop_id, sku)`. Đã nối lại ở cả create lẫn update; kiểm chứng
> bằng backend thật: tạo `TEST-SKU-001` → lưu đúng, tạo lại trùng → **409
> "Mã SKU đã tồn tại trong shop"**.

## 8. Chạy

```bash
docker compose up -d
cd mock-openAPI && .venv\Scripts\python.exe -m uvicorn main:app --port 4001 --reload
cd server      && .venv\Scripts\python.exe -m uvicorn app.main:app --port 4000 --reload
cd v-market    && npm run dev     # Simulator :3000+, MiniApp :8080+
```

Mở bằng **`localhost`**, không phải `127.0.0.1` — dev server chỉ bind IPv6.
