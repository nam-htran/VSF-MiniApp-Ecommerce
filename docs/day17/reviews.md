# Ngày 17 — Đánh giá sản phẩm

Ô "Optional" trong Plan cho phép chọn **tối đa một** tính năng thêm. Cuối
cùng làm hai: đánh giá và [voucher](../day3/vouchers-variants.md).

---

## 1. Chỉ người đã mua mới được đánh giá

Đây là toàn bộ giá trị của tính năng. Một ô đánh giá ai cũng gõ được thì
không phải đánh giá, mà là ô bình luận — và sao trung bình tính từ nó là số
vô nghĩa.

Cổng kiểm nằm ở `has_purchased`, đi ngược ba bảng:

```
orders (status = PAID)
  └── shop_orders
        └── order_items (product_id = ?)
```

Ba điều kiện, và **`PAID` là điều kiện quan trọng nhất**: đơn mới đặt chưa
trả tiền thì chưa mua. Nếu không có nó, người ta đặt đơn, đánh giá, rồi bỏ
không trả tiền — miễn phí.

Người mua chưa đủ điều kiện gọi `POST /products/{id}/reviews` nhận **403**.
Có `GET .../reviews/eligibility` để UI biết mà không cần thử-rồi-lỗi.

---

## 2. Một người một đánh giá cho mỗi sản phẩm

```python
UniqueConstraint("product_id", "user_id", name="uq_reviews_product_user")
CheckConstraint("rating BETWEEN 1 AND 5", name="ck_reviews_rating")
```

Ràng buộc ở **database**, không chỉ ở code. Mua lại lần hai không cho thêm
một phiếu bầu nữa; gửi lại là **sửa** đánh giá cũ (`upsert`), không tạo bản
mới.

Khoảng `1..5` cũng chặn ở DB — không có đường nào ghi được rating 0 hay 99,
kể cả khi validation ở tầng trên bị bỏ sót.

---

## 3. Sao trung bình đi cùng danh sách sản phẩm

`ratingAverage` và `ratingCount` không lưu trên bảng `products`. Chúng được
**tính bằng subquery** rồi left-join vào listing, cùng chỗ với `sold`:

```python
def _metric_subqueries():   # products/store.py
    # trung bình + đếm từ reviews, số đã bán từ đơn PAID
```

Lý do: một cột `rating_average` lưu sẵn là **con số thứ hai có thể lệch**.
Xoá một đánh giá, sửa một điểm — quên cập nhật một chỗ là sai vĩnh viễn.
Subquery chậm hơn chút nhưng không bao giờ sai.

Import cục bộ trong hàm để tránh vòng lặp import `products ↔ orders/reviews`.

---

## 4. Giao diện

`ReviewsSection` trên trang sản phẩm: điểm trung bình, số lượt, danh sách
bình luận, và nút viết đánh giá **chỉ hiện khi đủ điều kiện**.

Chọn sao bằng sheet với 5 ngôi sao bấm được, không dùng slider — trên màn
hình nhỏ, năm mục tiêu bấm rõ ràng dễ hơn một thanh trượt.

---

## 5. Dữ liệu demo phải mua thật

`seed_demo.py` **không insert thẳng review vào DB**. Nó không làm được — cổng
kiểm chặn ở server. Nên mỗi người mua demo phải:

1. đăng ký tài khoản trên mock,
2. đặt một giỏ 6–11 món,
3. **thanh toán qua IPN của cổng**,
4. rồi mới đánh giá ~75% số món đã mua.

Đó cũng là lý do **`sold` và số sao trong demo là số thật**, tính từ đơn đã
trả tiền, chứ không phải số trang trí.

Phân bố sao cố ý lệch về 4–5 (55% năm sao, 27% bốn sao, còn lại 3–1) và bình
luận có cả chê. Một bức tường toàn 5 sao đọc là giả ngay.

> Chính vì seed đi qua đường thật mà nó **phát hiện được sự cố**: có lần
> webhook của mock bị trỏ sai, và seed ra `0 đánh giá` — đơn tạo được nhưng
> không đơn nào thành `PAID`. Seed giờ đếm số đơn **thật sự** `PAID` thay vì
> đếm số người mua, nên một lần chạy hỏng không còn trông giống lần chạy tốt.
