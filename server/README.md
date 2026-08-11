# V-Market Backend

FastAPI backend là nguồn sự thật cho catalog, tồn kho, đơn hàng, thanh toán và
recommendation. Client không gửi giá cuối, quyền sở hữu hay trạng thái thanh
toán; server luôn đọc lại và kiểm tra trong PostgreSQL.

## Chức năng

- Đăng nhập qua V-App `authCode`, phát hành session JWT của V-Market.
- Shop, sản phẩm, biến thể, tồn kho, voucher, tìm kiếm và đánh giá.
- Giỏ hàng nhiều shop, báo giá, đặt hàng, giữ tồn kho và xử lý IPN.
- Địa chỉ giao hàng, reverse geocoding và luồng vận hành seller/admin.
- Lưu lịch sử xem và xếp hạng chính storefront theo đó, không phải một strip riêng.

Swagger chạy tại <http://127.0.0.1:4000/docs>.

## AI serving

Khi server khởi động:

1. `artifact_paths.py` tìm checkpoint Transformer tốt nhất và RQ-VAE mới nhất.
2. Transformer load một lần, ưu tiên CUDA nếu khả dụng.
3. Beam mask được dựng từ Semantic ID của sản phẩm `ACTIVE` trong PostgreSQL.
4. Jina và frozen RQ-VAE load một lần trên CPU để index sản phẩm mới nền.

`GET /products` là bề mặt recommendation duy nhất của storefront. Endpoint vẫn
public; bearer token nếu có **chỉ đổi thứ tự**. Trang chủ và tìm kiếm dùng chung
một feed đã xếp hạng, nên bấm vào một sản phẩm là sắp lại cả chợ chứ không lấp
một ô riêng.

Lịch sử xem đến từ hai nguồn, cùng đi qua một đường xếp hạng:

| Người dùng | Nguồn lịch sử | Server lưu gì |
|---|---|---|
| Đã đăng nhập | Bảng `product_views` | Có, kèm thứ hạng cache theo shopper |
| Chưa đăng nhập | `?seen=id,id,…` do máy khách gửi | Không lưu gì, không cache |

Khách vãng lai vẫn được recommend — bắt đăng nhập mới xếp hạng thì gần như
không xếp hạng cho ai. Lịch sử của họ nằm trên máy, đi kèm request, và server
đọc chứ không ghi. Danh sách bị cắt còn 10 phần tử như đường đăng nhập, nên
client không tự nới ngữ cảnh của mình được.

Không có nguồn nào thì `rankedBy` trả `null` và feed là shop window: đã bán,
rating rồi ID.

Có lịch sử thì dùng 10 lượt xem gần nhất, giữ cả lượt lặp, rồi đi theo thứ tự:

```text
Transformer Top-10 SID
→ exact full SID
→ prefix hai tầng nếu cụm thiếu sản phẩm
→ Semantic ID gần lịch sử, sâu trước: 3 tầng → 2 tầng → 1 tầng
```

Chuỗi này dừng ở đó. Thứ hạng **chỉ chứa những gì Semantic ID với tới** — vài
chục sản phẩm, bất kể catalog to bao nhiêu; đo được 29/200 với lịch sử 3 lượt
xem. Phần còn lại không được lấp bằng hàng bán chạy, mà để nguyên cho `else_`
trong `list_active` sắp: cùng một tiêu chí đã bán, lại thêm được tiebreak theo
rating mà bước lấp không có. Lấp đầy nghĩa là dựng cả catalog bằng Python để ra
đúng thứ tự mà SQL vẫn sắp.

Hệ quả: sản phẩm vừa xem không bị **đẩy xuống cuối** nữa, nó chỉ không được
nâng lên — nằm cùng nhóm với mọi sản phẩm mà model không nhắc tới.

Các beam được lấy **xen kẽ**: mỗi cụm góp tối đa 3 sản phẩm rồi nhường lượt cho
beam sau. Vét cạn từng cụm sẽ để một cụm chiếm trọn màn hình đầu — một cụm chứa
tới ~10 sản phẩm gần giống hệt nhau. Trong mỗi cụm vẫn xếp theo đã bán, rating và
ID để kết quả ổn định.

Thứ hạng được giữ suốt một lượt duyệt, nên **Transformer chạy một lần mỗi lần
tải trang chủ**, không phải mỗi trang khi cuộn. Đây trước hết là yêu cầu về
tính đúng: storefront đọc catalog theo từng trang, thứ hạng đổi giữa chừng sẽ
làm một sản phẩm xuất hiện hai lần hoặc biến mất.

Shopper đã đăng nhập có một entry riêng, xoá khi họ xem thêm sản phẩm. Khách
vãng lai dùng **một ô duy nhất** giữ câu trả lời gần nhất — một lượt duyệt gửi
cùng danh sách `seen` cho mọi trang nên một ô là đủ, và không tích trữ gì theo
số người truy cập. Hai khách xen kẽ nhau thì đẩy nhau ra và tính lại; thứ hạng
là hàm thuần của dữ liệu request mang theo nên trượt cache chỉ tốn thời gian,
không bao giờ sai.

Không có endpoint `/recommendations` riêng. Thay vào đó `GET /products` trả thêm
`rankedBy` — `transformer`, `semantic-id`, `popular`, hoặc `null` khi request
không có session. Cần trường này vì một thứ tự không tự nói được lý do: kết quả
từ Transformer và kết quả fallback bán chạy là cùng một danh sách sản phẩm, chỉ
khác trình tự. Related products không cần Transformer: lùi từ full SID sang
prefix hai tầng, một tầng rồi mới dùng popularity.

Sản phẩm mới hoặc thay đổi tên/mô tả được ghi với SID rỗng. Worker chạy Jina →
RQ-VAE theo batch, cập nhật SID có điều kiện để kết quả cũ không ghi đè nội dung
seller vừa sửa, sau đó refresh mask mà không reload Transformer.

Mỗi vòng quét, worker còn đối chiếu số Semantic ID trong DB với số mà mask đang
giữ và dựng lại nếu lệch. Ghi hàng loạt ngoài API — `scripts/seed_demo.py` gán
SID bằng một câu `UPDATE` — không refresh được mask, và mask cũ **không báo lỗi**:
beam search vẫn sinh kết quả tự tin, từ tập cụm mà catalog không còn dùng.

## Cấu hình

Copy file môi trường mẫu:

```bash
cp .env.example .env
```

Secret và địa chỉ triển khai nằm trong `.env`. Cấu hình model, batch semantic
và checkpoint resolver nằm trong `app/config.py`. Checkpoint local được tìm tại:

```text
../ai-recommendation/output/transformer/
../ai-recommendation/output/rq-vae/
```

`requirements.txt` dùng PyTorch 2.10.0 CUDA 12.6, cùng Transformers 5.14.1 và
Sentence Transformers 5.4.1 đã tạo artifact trên Kaggle.

## Chạy riêng backend

Khuyến nghị chạy cả stack bằng `pnpm dev` trong `v-market/`. Nếu chỉ chạy
backend:

```bash
docker compose up -d --wait

cd server
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m uvicorn app.main:app --port 4000 --reload
```

Backend vẫn cần mock V-App ở `4001` cho login/payment local. Health check:

```bash
curl http://127.0.0.1:4000/healthz
```

## Kiểm thử

```bash
.venv/bin/python -m pytest
```

Test integration cần PostgreSQL và mock-openAPI. Bộ test truncate các bảng nó
đụng tới; chạy xong cần seed lại nếu muốn tiếp tục dùng catalog demo.
