# Ngày 13 — Bảo mật nghiệp vụ

Không phải mật mã học, mà là **những chỗ một người dùng bình thường có thể
lấy thứ không phải của mình**. Tất cả kiểm ở backend; UI chỉ là trình bày.

---

## 1. Phân quyền

Ba vai trò: `BUYER` (mặc định), `SELLER` (kiếm được bằng cách mở shop),
`ADMIN` (người vận hành sàn).

| Kiểm | Ở đâu |
|---|---|
| AUTH-04 — người mua gọi endpoint người bán | `CurrentSeller` → 403 |
| AUTH-05 — người bán chạm dữ liệu shop khác | trong từng handler → **404** |
| ADMIN — đọc hàng đợi hoàn tiền | `CurrentAdmin` → 403 |

### Vì sao 404 chứ không 403

403 gián tiếp xác nhận **id đó có tồn tại**. Lặp lại vài nghìn lần là dò được
danh sách id hợp lệ của sàn. 404 cho cả "không có" lẫn "không phải của bạn"
thì không nói gì cả.

Áp dụng thống nhất: shop, sản phẩm, đơn hàng, lát đơn của shop, voucher, và
phiên thanh toán.

### Vai trò ADMIN đến từ config, không từ database

```bash
ADMIN_VAPP_USER_IDS=44444444-4444-4444-8444-444444444444
```

**Không có admin nào để cấp quyền cho admin đầu tiên.** Một endpoint
"cho tôi làm admin" là đúng thứ không nên xây. Danh sách được đọc lại **mỗi
lần đăng nhập**, nên thu hồi quyền là sửa config + đăng nhập lại, không phải
sửa dữ liệu.

### Vai trò đọc lại từ DB, không tin token

`current_user` đọc user từ database thay vì tin bản sao trong token. Quyền bị
thu hồi sau khi token phát ra thì phải có hiệu lực **ngay**, không đợi token
hết hạn.

---

## 2. Client không bao giờ định giá

Mọi endpoint tạo đơn nhận **id và số lượng**, không nhận tiền. Trường lạ như
`price`, `total`, `discount` trong request bị **bỏ qua hoàn toàn** — Pydantic
không khai thì không đọc.

Đã có test gửi hẳn `{"price": 1, "total": 1, "discount": 999999}`: đơn vẫn ra
đúng 500.000₫.

Voucher cũng vậy — mã client chọn chỉ là *đề nghị*, server kiểm lại.

---

## 3. Kiểm duyệt nội dung người bán

`app/products/moderation.py` chặn sản phẩm chứa từ khoá cấm, kiểm **cả khi
tạo lẫn khi sửa** — nếu chỉ chặn lúc tạo thì sản phẩm sạch có thể bị sửa
thành hàng cấm.

Khớp sau khi **bỏ dấu và bỏ hoa thường**, nên `thuốc lá`, `THUOC LA`,
`Thuoc  La` là một.

> **Bài học tiếng Việt:** không dùng từ cấm **một âm tiết**. `sung` chặn nhầm
> `kẹo sung sướng` và `quả sung`. Danh sách chỉ giữ cụm từ hai âm tiết trở
> lên. Test bắt được chuyện này.

Thông báo trả về **nêu đúng từ vi phạm** — "sản phẩm bị từ chối" không lý do
là một ticket hỗ trợ đang chờ xảy ra.

---

## 4. Nội dung không được đọc thành HTML

Người bán tự nhập tên và mô tả, nên **mọi response đều chứa chữ server này
không viết ra**.

`Content-Type: application/json` đã ngăn trình duyệt thực thi, và React
escape khi render — nhưng không phải consumer nào cũng vậy, và một body chứa
`<script>` chỉ cách một cú `innerHTML` bất cẩn là thành stored XSS.

Nên `SafeJSONResponse` phát `<`, `>`, `&` dưới dạng `<` `>`
`&`. **Giá trị không đổi** — `json.loads` trả lại đúng thứ người bán gõ
— nhưng byte trên đường truyền không còn đọc được thành thẻ HTML.

---

## 5. Giới hạn tần suất

`POST /orders` là thứ tốn kém nhất một client có thể gọi dồn: nó ghi dữ liệu
và khoá tồn kho. Nên chỉ endpoint đó có trần — **20 lần / 60 giây** cho mỗi
người gọi (theo token nếu có, theo IP nếu chưa đăng nhập).

Vượt thì trả **429 kèm `Retry-After`**, không phải im lặng bỏ request. Duyệt
hàng không bao giờ bị chặn.

> **Nói thẳng giới hạn:** đếm trong bộ nhớ tiến trình. Không sống qua
> restart, không cộng dồn giữa nhiều worker. Trung thực với một demo chạy một
> tiến trình, và cố ý không tô vẽ thành hơn thế — production thật đặt cái này
> ở Redis hoặc ở tầng trước ứng dụng.

---

## 6. Tải file

`POST /uploads`: **bất kỳ ai đã đăng nhập**, allowlist `image/jpeg|png|webp`,
tối đa 5MB. Là **allowlist chứ không phải blocklist** — liệt kê cái được phép
thì thứ chưa nghĩ tới sẽ bị chặn theo mặc định.

Không đòi SELLER vì người mở shop up banner/logo khi còn là BUYER (vai trò chỉ
lên sau khi shop tạo xong). Ranh giới đúng ở đây là **có phiên đăng nhập**,
không phải vai trò: ẩn danh vẫn bị 401, nên không thành free file host.

---

## 7. Cái chưa có

- **Chưa quét nội dung ảnh.** Chỉ kiểm content-type và kích thước; một ảnh
  cấm vẫn lọt.
- **Chưa có báo cáo vi phạm** để người mua tố sản phẩm.
- **Chưa có rate limit cho đăng nhập** — mock không có gì để brute force,
  nhưng V-App thật thì cần.
