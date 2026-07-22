# Ngày 3 — Shop và tài khoản

Ba việc:

| | | |
|---|---|---|
| 1 | Quản lý shop của người bán | xong |
| 2 | Bỏ tài khoản seed, đăng ký được tài khoản V-App | xong |
| 3 | Giao diện cơ bản cho MiniApp | chưa |

Mục 3 chưa làm — phần dưới chỉ nói về 1 và 2.

---

## 1. Vì sao bỏ tài khoản seed

Ngày 1 gán vai trò bằng một bảng cứng:

```python
_SEED_ROLES = {
    "2222…": ("SELLER", "seller-a"),
}
```

Ba tài khoản, vai trò dán sẵn theo UUID. Không mở thêm được tài khoản, và không có cách nào để một người bình thường trở thành người bán — thứ mà một sàn nhiều người bán bắt buộc phải có.

Nhưng **không** thay bằng đăng ký mật khẩu trong V-Market. MiniApp chạy bên trong V-App: người dùng đã đăng nhập V-App rồi mới mở được nó. Dựng một hệ đăng nhập song song vừa sai bản chất nền tảng, vừa là code chắc chắn bị xoá khi có credential thật.

Nên việc đăng ký được đặt đúng chỗ của nó: **`mock-openAPI/`**, tức là bên V-App.

```
POST /simulator/users    {name}      →  {user_id}     ← đăng ký với V-App
POST /simulator/authcode {user_id}   →  {authCode}
POST /auth/session       {authCode}  →  JWT           ← không đổi dòng nào
```

Luồng đăng nhập ngày 1 không phải sửa gì. Ngày có V-App thật, tắt mock đi là toàn bộ phần "đăng ký" biến mất cùng nó — không có dòng nào trong `server/` phải dọn.

---

## 2. Hai database, không phải một

Tài khoản V-App giờ nằm trong Postgres. Nhưng **database riêng**, không chung với V-Market.

```
vmarket-db  (1 container)
├── vmarket     ← server/
└── vapp_mock   ← mock-openAPI/
```

Lý do: `mock-openAPI/` đang đóng vai hệ thống của một công ty khác. Dùng chung một database thì sớm muộn có người viết `JOIN` qua bảng của V-App — chạy tốt, test xanh, và **chết ngay ngày ráp API thật**, vì lúc đó bảng kia nằm ở Vingroup.

Postgres **không join được across database**. Đó là giới hạn của engine, không phải quy ước — nên không cần ai phải nhớ luật. Dùng schema riêng thì vẫn join được, yếu hơn hẳn.

Cả hai database được tạo trong `docker/initdb/01-databases.sql`. Image `postgres` chỉ nhận **một** tên qua `POSTGRES_DB`, nên biến đó lùi về vai trò bootstrap và mọi database nằm chung một chỗ, đọc là thấy hết.

Script chỉ chạy **khi volume trống**, nên sửa nó thì phải `docker compose down -v`.

Bảng thì không nằm trong SQL — cả hai app đều gọi `create_all` lúc khởi động, để schema chỉ có một nguồn là các model.

### Cái cố ý không cho vào DB

`authCode` và `access_token` vẫn nằm trong RAM của mock.

Chúng sống 60 giây và 1 giờ. Mất khi restart là **đúng** — token thật cũng không sống qua việc nhà cung cấp khởi động lại. Đưa vào DB chỉ thêm việc dọn dòng hết hạn mà không được gì.

Ranh giới ở đây là **tuổi thọ dữ liệu**: cái gì phải sống lâu thì vào DB, cái gì là vé tạm thì để trong bộ nhớ.

### Lỗi mà việc này chữa

Trước đó hai bên lệch tuổi thọ: `server/` lưu Postgres, mock lưu RAM. Tạo tài khoản → mở shop → restart mock. Postgres vẫn giữ dòng `users` trỏ tới một `vapp_user_id` mà V-App **không còn biết**. Đăng nhập lại nhận `Unknown user_id`, và không chữa được ngoài xoá DB.

Seed cứng che được lỗi này vì 3 ID luôn quay lại. Bỏ seed thì lỗi lộ ra ngay — nên hai việc phải làm cùng lúc.

---

## 3. Vai trò kiếm được, không phát sẵn

```python
role: Mapped[str] = mapped_column(default="BUYER")
```

Ai đăng nhập cũng là `BUYER`. Mở shop thì thành `SELLER`:

```python
await users.promote_to_seller(session, user)
```

Kéo theo một điều bắt buộc: `POST /shops` **không được** đòi vai trò `SELLER`. Nếu đòi thì không ai lên seller được — muốn tạo shop phải là seller, muốn là seller phải tạo shop. Nên endpoint đó nhận `CurrentUser` (bất kỳ ai đã đăng nhập), còn `GET /shops/me` và `PATCH /shops/{id}` mới cần `CurrentSeller`.

Cột `seller_id` bị bỏ. Nguồn duy nhất ghi vào nó là `_SEED_ROLES`; bỏ bảng đó đi thì nó thành cột không ai ghi. Quan hệ "ai sở hữu shop nào" đã nằm ở `shops.owner_id` rồi, giữ thêm con trỏ ngược chỉ tạo hai chỗ phải đồng bộ. `sellerId` cũng ra khỏi JWT theo.

Vai trò đổi giữa chừng vẫn có hiệu lực ngay, vì `deps.py` đọc lại user từ DB mỗi request thay vì tin bản sao trong token — test `test_opening_a_shop_turns_a_buyer_into_a_seller` kiểm đúng chỗ này: cùng một token, trước khi mở shop `GET /shops/me` trả 403, sau khi mở trả 200, không cần đăng nhập lại.

---

## 4. API shop

| | | Ai gọi được |
|---|---|---|
| `POST /shops` | Mở shop, đồng thời lên SELLER | ai đã đăng nhập |
| `GET /shops/me` | Shop của mình | SELLER |
| `PATCH /shops/{id}` | Sửa shop của mình | SELLER, và phải là chủ |
| `GET /shops/{id}` | Xem shop | công khai |

Hai chi tiết đáng đọc kỹ.

**Một người một shop, chặn ở DB:**

```python
owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
```

Route bắt `IntegrityError` rồi trả 409, thay vì kiểm tra trước bằng `if`. Hai request đồng thời sẽ cùng đọc thấy "chưa có shop" rồi cùng tạo — ràng buộc DB thì không lách được.

**Chạm shop người khác trả 404, không phải 403:**

```python
if shop is None or shop.owner_id != seller.id:
    raise HTTPException(404, detail="Shop not found")
```

403 gián tiếp xác nhận shop đó tồn tại, biến endpoint thành công cụ dò ID hợp lệ.

---

## 5. Chạy và test

```bash
docker compose up -d          # lần đầu sau thay đổi này: down -v trước

cd mock-openAPI
.venv\Scripts\python.exe -m uvicorn main:app --port 4001 --reload

cd server
.venv\Scripts\python.exe -m uvicorn app.main:app --port 4000 --reload
.venv\Scripts\python.exe -m pytest
```

20 ca: 8 contract, 6 auth-flow, 6 shops.

> Test có đăng ký tài khoản vào `vapp_mock` và không dọn lại, nên chạy nhiều lần sẽ thấy vài tài khoản trùng tên trong `/simulator/users`. Không ảnh hưởng ca test nào — dọn bằng `docker compose down -v` nếu thấy rối.

---

## 6. Còn lại của ngày 3

Giao diện cơ bản cho MiniApp, ít nhất ba màn:

- Chọn hoặc tạo tài khoản V-App, rồi đăng nhập (thay cho JSAPI `getAuthCode`)
- Mở shop / xem shop của mình
- Danh sách shop cho người mua

Chỗ này là nơi consent hai giai đoạn cuối cùng nhìn thấy được: tài khoản mới sẽ đi qua `CONSENT_REQUIRED` rồi mới vào, còn tài khoản cũ vào thẳng.
