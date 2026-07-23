# Voucher và phân loại sản phẩm

Hai tính năng làm sau [orders.md](orders.md), và cả hai đụng vào cùng một
thứ nhạy cảm: **giá và tồn kho**. Nên nguyên tắc chung của cả hai là *chỉ có
một nguồn sự thật*.

---

## 1. Voucher

Voucher là **dòng dữ liệu thật**, không phải chữ quảng cáo. Mỗi mã thuộc một
shop, hoặc thuộc về không ai cả (`shop_id` NULL — toàn sàn), có thể giới hạn
theo **danh mục**, và sống giữa `starts_at` / `ends_at`.

Hết hạn thì **tự biến mất**: server chỉ trả về mã đang trong khung giờ. Không
cần job dọn, và không thể lỡ quảng cáo một chương trình đã kết thúc.

### Điều quan trọng nhất

Chỉ có **một** hàm tính giảm giá: `discount_for`. Giá hiện trên card, báo giá
ở checkout, và số tiền thật bị trừ đều đi qua nó.

> Đây là lỗi duy nhất thực sự chết người của một tính năng giảm giá:
> **quảng cáo một đằng, tính tiền một nẻo.**

Vì vậy checkout không tự cộng giá nữa mà gọi `POST /orders/quote` — cùng
cách nhóm theo shop, cùng phép tính voucher mà đơn hàng sẽ dùng.

### `min_order` đo trên phần đủ điều kiện

"Giảm cho đơn thời trang từ 300k" nghĩa là **300k tiền quần áo**, không phải
300k tiền gì cũng được rồi nhét vào một cái áo. Nên `eligible_subtotal` lọc
theo danh mục trước, rồi mới so ngưỡng.

### Người mua thấy cả mã chưa dùng được

Checkout liệt kê **mọi** mã của shop. Mã chưa đủ điều kiện thì **làm mờ,
không bấm được, và ghi lý do** — `Cần thêm 4.310.000₫`. Một mã người mua
không nhìn thấy là một mã họ không thể phấn đấu tới.

Chọn mã được, nhưng mã client gửi lên chỉ là **đề nghị**: server kiểm lại
(còn hạn, đúng shop, thực sự giảm được tiền) và **âm thầm quay về mã tốt
nhất** nếu không hợp lệ — không văng lỗi giữa lúc thanh toán.

---

## 2. Phân loại (variants)

Người bán khai nhóm lựa chọn — `Size`, `Màu sắc` — và **số lượng cho từng tổ
hợp**. Tên nhóm do seller đặt, nên shop bán sơn ghi `Dung tích` mà không phải
đổi schema.

### Tồn kho nằm ở đúng một nơi

- Sản phẩm **không** khai phân loại → tồn kho ở `products.stock`, y như cũ.
- Khai rồi → tồn kho **chỉ** ở `product_variants`, và storefront hiện tổng.

Giữ thêm một con số tổng trên `products` sẽ là hai nguồn sự thật cho đúng cái
số không được phép sai.

### Khoá đúng dòng sẽ bị trừ

Checkout khoá **dòng biến thể** với sản phẩm có phân loại, khoá **dòng sản
phẩm** với sản phẩm thường. Mua size M không làm hụt size L.

Sản phẩm có phân loại mà client không chọn thì server **từ chối**, không đoán
bừa một size.

### Một lỗi đáng nhớ

Khi thêm bước đọc sản phẩm **không khoá** trước bước khoá, `session.get` trả
object từ identity map và **không chạy `SELECT … FOR UPDATE`**. Khoá biến mất
không một tiếng động, hai người cùng mua món cuối đều thắng.

`populate_existing=True` là thứ giữ INV-05 sống. Test
`test_two_buyers_race_for_the_last_unit` bắt được — đúng lý do nó tồn tại.

### Thứ tự do seller quyết

`product_variants.position` giữ thứ tự người bán nhập. Sắp theo `id` thì uuid
cho ra `39, 41, 42, 43, 40`; sắp theo nhãn thì `2XL` đứng trước `S`. Chỉ
người gõ danh sách mới biết thứ tự đúng.

### Hoá đơn giữ nhãn

`order_items.variant_label` chép lại lúc mua. Seller xoá option ngày mai thì
hoá đơn hôm qua vẫn đọc được "Đen / L".

---

## 3. SKU

Mã hàng của người bán, **duy nhất trong shop, không duy nhất toàn sàn**.

Nếu duy nhất toàn sàn thì khi shop A đăng `IP15-128-BLACK`, không shop nào
khác dùng được mã đó nữa — kể cả khi họ bán đúng cái máy ấy. Điều đó đi ngược
bản chất sàn nhiều người bán. Định danh toàn sàn đã có sẵn: `products.id`.

Các sàn thật cũng vậy: Shopee, Lazada (`SellerSku`), Amazon (`SellerSKU`,
còn định danh toàn cầu là ASIN do sàn cấp).

---

## 4. Kiểm duyệt nội dung

[`app/products/moderation.py`](../../server/app/products/moderation.py) chặn
sản phẩm chứa từ khoá cấm khi tạo và khi sửa, bỏ dấu và không phân biệt hoa
thường — `thuốc lá`, `THUOC LA`, `Thuoc  La` là một.

**Bài học từ tiếng Việt:** không dùng từ cấm **một âm tiết**. `sung` chặn
nhầm `kẹo sung sướng` và `quả sung`. Danh sách chỉ giữ cụm từ hai âm tiết trở
lên.

---

## 5. Test

`test_vouchers.py` (12), `test_variants.py` (5), `test_matrix_guards.py`
(11). Đáng chú ý:

- giá trên card = báo giá checkout = tiền thật bị trừ
- mã hết hạn không giảm gì và không hiện ở đâu
- mua size này không hụt size kia
- tranh nhau cái cuối của **một size** vẫn đúng một người thắng
- sửa phân loại giữ nguyên id, đơn cũ không trỏ vào khoảng không
