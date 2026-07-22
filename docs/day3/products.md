# Sản phẩm

Bảng `products` trong database `vmarket`, cùng chỗ với `users` và `shops`.

**Không** tách database riêng như `vapp_mock`. Lần đó tách là để Postgres **cấm** join qua hệ thống của bên khác. Ở đây ngược lại: đơn hàng phải join tới sản phẩm, sản phẩm phải join tới shop — và cần khoá ngoại để không có dòng hàng nào trỏ tới sản phẩm không tồn tại.

---

## 1. Model

```python
class Product(Base):
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(primary_key=True)
    shop_id: Mapped[str] = mapped_column(ForeignKey("shops.id"), index=True)
    name: Mapped[str]
    description: Mapped[str]
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    stock: Mapped[int]
    image_url: Mapped[str | None]
    status: Mapped[str] = mapped_column(default="ACTIVE")
```

**Giá là `Numeric`, không phải `Float`.** Trong dấu phẩy động nhị phân `0.1 + 0.2 != 0.3`; cộng vài chục dòng đơn hàng là số tiền lệch khỏi con số người mua đã nhìn thấy.

**`HIDDEN` thay cho xoá.** Người bán gỡ hàng khỏi gian hàng nhưng đơn cũ vẫn trỏ tới nó — xoá thật là làm hỏng lịch sử đơn hàng.

## 2. Ràng buộc ở tầng database

```python
CheckConstraint("stock >= 0", name="ck_products_stock_non_negative")
CheckConstraint("price >= 0", name="ck_products_price_non_negative")
```

Đây là **lớp phòng thủ cuối** cho INV-05. Lúc thanh toán sẽ khoá dòng bằng `SELECT ... FOR UPDATE` rồi mới trừ kho, nhưng nếu logic đó có bug thì database vẫn từ chối bán cái thứ mười của món chỉ còn chín.

Đã thử chọc thẳng vào Postgres, bỏ qua toàn bộ code Python:

```
ERROR: new row for relation "products" violates check constraint
       "ck_products_stock_non_negative"
```

Cùng nguyên tắc với `unique` trên `shops.owner_id`: chặn ở nơi không lách được, không chặn bằng câu `if`.

---

## 3. API

| | Ai gọi được |
|---|---|
| `GET /shops/{shop_id}/products` | công khai |
| `GET /products/{product_id}` | công khai |
| `GET /products/mine` | chủ shop |
| `POST /products` | chủ shop |
| `PATCH /products/{product_id}` | chủ shop, và phải đúng shop của mình |

### Shop lấy từ người gọi, không lấy từ request

`CreateProductRequest` **không có** trường `shopId`. Có thì người bán chỉ cần đổi một chữ trong body là đăng hàng vào gian của người khác — kiểm quyền dựa trên dữ liệu client gửi lên thì không phải kiểm quyền.

Test khẳng định thẳng: `assert body["shopId"] == shop_id`, trong khi request chưa hề nhắc tới shop nào.

### Phân quyền hai chặng

Khác `shops` chỉ một chặng, ở đây phải đi hai: sản phẩm thuộc shop nào → shop đó của ai.

Cả ba trường hợp — sản phẩm không tồn tại, của người khác, người gọi chưa có shop — đều trả **404** như nhau, để không ai dò được id nào có thật.

### Hai endpoint danh sách, không phải một endpoint có cờ

| | Hàng ẩn |
|---|---|
| `GET /shops/{id}/products` | không bao giờ trả |
| `GET /products/mine` | có |

Gộp làm một với tham số `includeHidden=true` thì chỉ cần quên một lần kiểm quyền là lộ hàng ẩn ra gian hàng. Tách hai thì endpoint công khai **không có đường nào** để hỏi hàng ẩn.

Thứ tự khai báo cũng quan trọng: `/products/mine` phải đứng **trước** `/products/{product_id}`, không thì FastAPI hiểu `"mine"` là một id.

### Giá trả về là số, không phải chuỗi

VND là đồng nguyên, nằm rất xa ngưỡng 2^53 nơi số trong JSON mất chính xác. Thứ phải tránh không phải kiểu dữ liệu, mà là **tính toán ở client** — tổng tiền luôn do server tính.

---

## 4. Test

6 ca trong `tests/test_products.py`, tổng cả dự án **26 ca**.

- người bán thêm hàng vào shop của mình, và `shopId` đến từ phiên đăng nhập
- người mua không thêm được → 403
- người bán không sửa được hàng của shop khác → 404, và giá cũ còn nguyên
- hàng `HIDDEN` biến mất khỏi gian hàng và khỏi trang chi tiết, nhưng chủ shop vẫn thấy
- `stock` âm bị chặn → 422
- gian hàng xem được khi không có token

`stock` bị chặn ở **hai** lớp: Pydantic `ge=0` trả 422, và `CHECK` trong Postgres chặn mọi thứ lọt qua. Test kiểm lớp ngoài; lớp trong kiểm bằng SQL trực tiếp như ở §2.

---

## 5. Tiếp theo — đơn hàng

Đã chốt mô hình **B**: đơn cha, tách thành đơn con mỗi shop một cái.

```
orders          ← trả tiền một lần, ở đây
└── shop_orders ← giao hàng, trạng thái, huỷ — mỗi shop một dòng
    └── order_items
```

Lý do: **thanh toán có một, giao hàng có nhiều**. Shop A gửi trong 2 tiếng, shop B ba ngày sau — nhét chung một đơn thì trạng thái của đơn đó không có câu trả lời đúng.

Điểm làm B thành B: `order_items` gắn vào **`shop_orders`**, không gắn vào `orders`. Treo thẳng vào `orders` thì chỉ là dán nhãn shop lên từng dòng hàng, tức vẫn là mô hình A.

Hai loại trạng thái tách biệt:

| Bảng | Trạng thái |
|---|---|
| `orders` | thanh toán: `PENDING` → `PAID` / `FAILED` |
| `shop_orders` | giao hàng: `CONFIRMED` → `SHIPPING` → `DELIVERED` / `CANCELLED` |

B cũng giải sẵn hai thứ A không giải được: phí ship mỗi shop một khác (quy chế §5.2.1 bắt hiện rõ trước khi xác nhận), và COV Order Sync của V-App chỉ có **một** `seller_merchant_id` cho mỗi đơn.

Khi làm, nhớ: `order_items` phải **chép tên và giá lúc đặt**, không chỉ trỏ khoá ngoại — người bán sửa giá ngày mai thì hoá đơn hôm qua vẫn phải là giá cũ.
