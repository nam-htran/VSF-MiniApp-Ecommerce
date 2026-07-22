# Nền móng frontend

Mới có tầng gọi API. Chưa có màn hình nào.

---

## 1. Đã kiểm chứng: Simulator gọi được backend

Đây là câu hỏi lớn nhất trước khi viết frontend, vì nếu sai thì cách ghép MiniApp với `server/` phải làm lại từ đầu.

Kết quả: **gọi được**. Gửi thẳng vào proxy của CLI và nhận về dữ liệu thật từ Postgres.

```
HTTP status qua proxy: 200
 - Sách cũ Hà Nội
 - Tạp hoá Cô Chi
 - Điện máy Bình Minh
```

Chuỗi đầy đủ: cầu nối MiniApp → proxy Node của CLI → `server/:4000` → Postgres.

Lý do chạy được: trong Simulator, request **không** đi từ trình duyệt mà vòng qua middleware `/http` chạy bằng Node **trên máy dev**. Nên `127.0.0.1` trỏ về đúng loopback của máy mình. Trên điện thoại thật thì không còn proxy đó — xem [platform-constraints.md](platform-constraints.md) §2.

---

## 2. `src/api/client.ts`

Nơi **duy nhất** trong app quyết định gọi mạng thế nào.

```ts
const BASE = import.meta.env.VITE_API_BASE;

export async function apiRequest<T>(path, init = {}): Promise<T>
```

Vì sao phải gom một chỗ: trong V-App **không có `fetch`**, mọi request đi qua `apisAsync.request` và chỉ chạy HTTPS. Ngày chuyển sang test máy thật, thứ phải đổi là **một dòng trong `.env`**, không phải code.

### Phát hiện cầu nối, kèm cảnh báo to tiếng

```ts
const hasBridge = () =>
  typeof window !== 'undefined' && Boolean((window as { vsf?: unknown }).vsf);
```

Ngoài V-App — tab trình duyệt thường, unit test — `window.vsf` không tồn tại, và `apisAsync` **ném lỗi ngay khi truy cập thuộc tính** chứ không trả `undefined`. Nên phải kiểm trước.

Khi không có cầu nối thì rơi về `fetch`, nhưng kèm `console.warn`. Cố ý ồn ào: nếu cảnh báo đó xuất hiện **trong Simulator** thì nghĩa là cầu nối hỏng, và code chạy được ở đó sẽ chết trên máy thật nơi `fetch` không tồn tại. Im lặng ở đây là để bug đi xa hơn.

---

## 3. Cấu hình

| File | |
|---|---|
| `.env` | `VITE_API_BASE=http://127.0.0.1:4000` — bị gitignore |
| `.env.example` | bản mẫu, có commit |

Vite chỉ đọc `.env` **lúc khởi động**. Sửa giữa chừng phải chạy lại `v-miniapp-cli dev`.

---

## 4. Chạy

```bash
docker compose up -d

cd mock-openAPI && .venv\Scripts\python.exe -m uvicorn main:app --port 4001
cd server      && .venv\Scripts\python.exe -m uvicorn app.main:app --port 4000
cd v-market    && npm run dev
```

Simulator ở `http://localhost:3000`, MiniApp ở `http://localhost:8080`.

> Phải dùng **`localhost`**, không dùng `127.0.0.1`. Dev server của CLI chỉ bind IPv6, nên `http://127.0.0.1:8080` báo không kết nối được — trông y hệt như server chưa chạy.

---

## 5. Chưa làm

Toàn bộ màn hình. `client.ts` hiện **chưa có gì gọi tới**, nên nó compile được nhưng chưa chạy dòng nào — đường ống đã kiểm chứng, còn cách gọi thì chưa.

Khi dựng màn hình, nhớ hai thứ ở [platform-constraints.md](platform-constraints.md): đường dẫn **một tầng** (`/product?id=123`), và trang chủ **không được chặn bởi đăng nhập**.
