# Đơn hàng — đặt, trả tiền, giao

Nối tiếp [products.md §5](products.md#5-tiếp-theo--đơn-hàng), nơi đã chốt mô
hình **B**. Đây là phần đã dựng thật: đặt hàng, thanh toán qua cổng giả
lập, và người bán xử lý giao hàng.

---

## 1. Model B, như đã dựng

```
orders          ← trả tiền một lần
└── shop_orders ← giao hàng, mỗi shop một dòng
    └── order_items ← ảnh chụp tên/giá lúc đặt
```

Hai loại trạng thái **tách biệt**, không dùng chung một cột:

| Bảng | Trạng thái | Ai đổi |
|---|---|---|
| `orders` | `PENDING` → `PAID` / `FAILED` / `CANCELLED` | cổng thanh toán (IPN) |
| `shop_orders` | `CONFIRMED` → `SHIPPING` → `DELIVERED` / `CANCELLED` | người bán |

Thanh toán có **một**, giao hàng có **nhiều**: shop A gửi trong 2 tiếng, shop
B ba ngày sau. Một cột trạng thái cho cả đơn thì không trả lời nổi câu "đơn
này tới đâu rồi" — nên trạng thái giao nằm trên từng `shop_orders`.

---

## 2. Đặt hàng: tiền và tồn kho không đến từ client

Client chỉ gửi **id sản phẩm + số lượng**. Giá đọc lại từ DB trong đúng
giao dịch khoá tồn kho, nên giỏ cũ hay giỏ bị sửa không mua được theo giá
hôm qua.

```python
for product_id in sorted(wanted):          # khoá theo thứ tự cố định
    product = await session.get(Product, product_id, with_for_update=True)
```

Ba điểm cố ý:

- **Khoá theo thứ tự đã sắp** — hai checkout khoá `{A,B}` và `{B,A}` sẽ
  deadlock; cùng khoá theo thứ tự sắp thì không.
- **Tất-cả-hoặc-không** — thiếu hàng một nửa thì cả đơn bị từ chối (409),
  không âm thầm bỏ nửa hết hàng và giao khác với cái người mua đã xác nhận.
- **`order_items` chép tên/giá lúc đặt** — hoá đơn là bức ảnh, không phải
  cửa sổ. Người bán đổi giá ngày mai, receipt hôm qua giữ nguyên.

Đơn vừa đặt ở trạng thái `PENDING`: đã tạo, chưa trả tiền.

---

## 3. Thanh toán: cổng giả lập + IPN ký

Quy chế §5.1.2 **cấm COD** — tiền phải đi qua cổng của sàn. Nên có một cổng
giả lập, và cổng báo về server bằng **IPN** (thông báo server-to-server),
đúng hình dạng cổng thật.

IPN ký bằng **HMAC-SHA256** trên `f"{orderId}|{amount}|{status}"` với khoá
chung. Server verify trước khi tin:

```python
if settings.payment_verify_hash and not verify_hash(secret, order_id, amount, status, secure_hash):
    raise HTTPException(400, "Bad signature")   # so sánh hằng thời gian
```

- **Số tiền so với `order.total` của chính đơn** — IPN bị sửa không trả
  thiếu hơn số phải trả được.
- **Idempotent** — cổng retry tới khi nhận 200, nên cùng một IPN có thể tới
  nhiều lần; IPN cho đơn đã `PAID` là thành công, không phải lỗi.

Chỉ khi `PENDING → PAID` xong, đơn mới thành việc thật cho người bán.

---

## 4. Giao hàng: người bán đẩy trạng thái

Nửa còn lại của model B. Người bán làm việc trên **queue của shop mình**:

```
GET   /orders/shop?status=SHIPPING   → các lát đơn của shop mình
PATCH /orders/shop/{id}  {status}    → đẩy một lát tiến một bước
```

Bốn ràng buộc, tất cả ở tầng server (không bao giờ chỉ ở UI):

- **Chỉ đơn `PAID` hiện ra.** Chưa trả tiền thì chưa có gì để giao —
  `list_for_shop` join lên `orders` và lọc `status == "PAID"`.
- **Một bước một.** `CONFIRMED → SHIPPING → DELIVERED`; server chỉ nhận
  đúng bước kế tiếp hợp lệ, nên bấm hai lần hay nút cũ không nhảy cóc hay
  lùi được.

  ```python
  expected = _FULFILMENT_NEXT.get(shop_order.status)   # {"CONFIRMED":"SHIPPING", "SHIPPING":"DELIVERED"}
  if target != expected:
      return shop_order, order, [], "INVALID_TRANSITION"   # → 409
  ```

- **Khoá theo shop của người gọi (AUTH-05).** `PATCH` giới hạn vào shop của
  seller đang gọi; chạm lát của shop khác trả **404**, để không dò được id
  nào tồn tại — cùng luật với shop và order ở chỗ khác.
- **`CANCELLED` không nằm trong bậc thang.** Huỷ sau khi đã trả tiền nghĩa
  là hoàn tiền, mà cổng giả lập chưa mô hình hoá; nên endpoint này không
  nhận `CANCELLED`.

Route seller đặt **trên** `GET /orders/{order_id}` trong file: đăng ký
trước thì `/orders/shop` khớp trước, không bị route bắt-tất-cả `{order_id}`
nuốt mất chữ "shop".

---

## 5. Test

`tests/test_orders.py` (6), `tests/test_payments.py` (6),
`tests/test_fulfilment.py` (6). Fulfilment kiểm:

- chỉ đơn `PAID` vào queue; đơn chưa trả tiền thì không
- đi đúng `CONFIRMED → SHIPPING → DELIVERED`; nhảy cóc hoặc đi tiếp sau
  `DELIVERED` → 409
- seller khác không thấy và không đẩy được lát của shop mình (404)
- lọc theo `status` thu hẹp đúng queue
- buyer chưa có shop gọi endpoint seller → 403
