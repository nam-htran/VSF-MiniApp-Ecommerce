# Ngày 9 — Người bán xử lý đơn, và trang cửa hàng

Nửa còn lại của model B. Người mua đã trả tiền một lần; giờ **mỗi shop tự
giao phần của mình**.

---

## 1. Hàng đợi của người bán

```
GET   /orders/shop?status=SHIPPING   → các lát đơn của shop mình
PATCH /orders/shop/{id}  {status}    → đẩy một lát tiến một bước
```

Bốn ràng buộc, tất cả ở server — không bao giờ chỉ ở UI:

**Chỉ đơn `PAID` hiện ra.** Chưa trả tiền thì chưa có gì để giao;
`list_for_shop` join lên `orders` và lọc `status == "PAID"`.

**Một bước một.** `CONFIRMED → SHIPPING → DELIVERED`. Server chỉ nhận đúng
bước kế tiếp hợp lệ, nên bấm hai lần hay một nút cũ trên màn hình chưa refresh
không nhảy cóc và không lùi được.

**Khoá theo shop người gọi.** Chạm lát đơn của shop khác trả **404**, không
phải 403 — 403 gián tiếp xác nhận id đó tồn tại, biến endpoint thành công cụ
dò.

**`CANCELLED` không nằm trong bậc thang.** Huỷ sau khi đã thu tiền nghĩa là
hoàn tiền, mà cổng giả lập chưa mô hình hoá. Không đưa vào còn hơn đưa vào rồi
mất dấu tiền.

> Route seller đăng ký **trên** `GET /orders/{order_id}` trong file. FastAPI
> khớp theo thứ tự đăng ký; đặt sau thì `/orders/shop` bị route bắt-tất-cả
> nuốt mất, `order_id` thành chuỗi `"shop"`.

Hoá đơn gửi cho người bán mang thêm **địa chỉ giao và ngày đặt** — thứ cần để
gói hàng, mà bản dành cho người mua không lặp lại ở từng shop.

---

## 2. Trang cửa hàng

`/shop?id=` là trang công khai, tới được từ **mọi chỗ có tên shop**: trang sản
phẩm, chi tiết đơn, giỏ hàng, tóm tắt thanh toán, và card ngoài trang chủ.

Banner và logo là **ảnh người bán tự tải lên** (`image_url` là banner,
`logo_url` là logo). Chưa có thì hiện dải màu thương hiệu — trang không bao
giờ trông vỡ.

### Trang quản lý *chính là* trang cửa hàng

Không có dashboard riêng. Chủ shop mở trang shop của mình thì thấy thêm:

- **cây bút** ở góc banner để sửa thông tin shop tại chỗ;
- ba tab **Sản phẩm / Đơn hàng / Mã giảm** thay cho các dải sản phẩm công
  khai.

Lý do: người bán và người mua nhìn cùng một trang thì người bán **thấy đúng
cái khách thấy**. Một dashboard tách rời luôn trôi khỏi thực tế.

`/seller` giờ chỉ còn một việc — shop chưa có thì hiện form mở shop, có rồi
thì chuyển thẳng sang `/shop`.

---

## 3. Thẻ cửa hàng trong trang sản phẩm

`ShopPreview` là một cửa hàng thu nhỏ: banner phủ toàn thẻ, logo và tên đè
lên trên (có gradient tối ở đáy để chữ đọc được), rồi **sản phẩm khác của
shop** cuộn ngang ngay trong thẻ.

Nó **tự fetch** shop và sản phẩm, vì chi tiết sản phẩm chỉ mang theo *tên*
shop chứ không có banner. Không tải được thì component **không render gì** —
thà thiếu một thẻ còn hơn một khung trống.

> Bài học từ ảnh seed: **đừng nướng tên shop vào banner**. Tên luôn được vẽ
> cạnh banner, nên nướng vào sẽ hiện hai lần, và mọi khung crop (như thẻ nhỏ
> này) sẽ cắt đôi bản nướng.

---

## 4. Ảnh tải lên

`POST /uploads` — chỉ người bán, chỉ `image/jpeg|png|webp`, tối đa **5MB**,
lưu vào `server/uploads/` và trả về **URL tuyệt đối** dựng từ
`request.base_url`.

Phải là URL tuyệt đối vì MiniApp chạy ở origin khác backend; đường dẫn tương
đối sẽ trỏ vào Vite dev server và 404.

Upload dùng `fetch` trực tiếp, **không đi qua `apiRequest`** — transport chỉ
biết JSON, còn đây là `multipart/form-data`.

> `.gitignore` phải viết `/uploads/` có gạch chéo đầu. Viết `uploads/` sẽ
> khớp luôn cả module code `server/app/uploads/`.

---

## 5. Xoá sản phẩm — xoá thật hay lưu trữ, tuỳ đã bán chưa

`DELETE /products/{id}` (chỉ chủ shop). Một sản phẩm **không thể xoá vô tư**:
`order_items.product_id` là khoá ngoại tới `products`, và mỗi dòng đơn cũ chụp
lại tên/giá từ sản phẩm đó. Xoá thẳng sẽ hoặc bị DB từ chối, hoặc làm hỏng
lịch sử đơn của người đã mua.

Nên server tự chọn một trong hai, dựa trên **đã từng có đơn hay chưa**:

| Tình huống | Kết quả | `outcome` |
|---|---|---|
| Chưa ai đặt | Xoá thật — cả `product_variants` và `reviews` đi kèm | `deleted` |
| Đã bán ít nhất một lần | Đổi trạng thái sang `ARCHIVED` | `archived` |

`ARCHIVED` là trạng thái thứ ba bên cạnh `ACTIVE`/`HIDDEN`: **biến mất khỏi mọi
danh sách**, kể cả trang quản lý của chính người bán (`list_for_shop` lọc
`status != 'ARCHIVED'` ngay cả khi `include_hidden`), nhưng hàng đã đặt vẫn trỏ
tới được. `place_order` vốn đã đòi `status == 'ACTIVE'`, nên hàng lưu trữ không
mua được nữa.

Giao diện xác nhận trước khi xoá, và **nói đúng cái đã xảy ra**: `deleted` →
"Đã xoá", `archived` → "Đã gỡ khỏi cửa hàng (vẫn giữ trong đơn đã bán)" — để
người bán không hoang mang khi thấy sản phẩm còn nằm trong một đơn cũ.

> Kiểm bằng backend thật, cả hai nhánh: sản phẩm mới tạo rồi xoá → `deleted`,
> mất khỏi danh sách; sản phẩm được đặt một đơn rồi xoá → `archived`, mất khỏi
> danh sách người bán nhưng đơn của người mua **vẫn hiện tên nó**, và
> `GET /products/{id}` công khai trả **404**.

> Không đối xứng có chủ đích: **ẩn** (`HIDDEN`) là nút mềm hơn ngay phía trên,
> cho người bán chỉ muốn tạm gỡ khỏi kệ mà chưa xoá hẳn.
