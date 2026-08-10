# V-Market Backend

FastAPI backend là nguồn sự thật cho catalog, tồn kho, đơn hàng, thanh toán và
recommendation. Client không gửi giá cuối, quyền sở hữu hay trạng thái thanh
toán; server luôn đọc lại và kiểm tra trong PostgreSQL.

## Chức năng

- Đăng nhập qua V-App `authCode`, phát hành session JWT của V-Market.
- Shop, sản phẩm, biến thể, tồn kho, voucher, tìm kiếm và đánh giá.
- Giỏ hàng nhiều shop, báo giá, đặt hàng, giữ tồn kho và xử lý IPN.
- Địa chỉ giao hàng, reverse geocoding và luồng vận hành seller/admin.
- Lưu lịch sử xem và trả recommendation cho trang chủ/chi tiết sản phẩm.

Swagger chạy tại <http://127.0.0.1:4000/docs>.

## AI serving

Khi server khởi động:

1. `artifact_paths.py` tìm checkpoint Transformer tốt nhất và RQ-VAE mới nhất.
2. Transformer load một lần, ưu tiên CUDA nếu khả dụng.
3. Beam mask được dựng từ Semantic ID của sản phẩm `ACTIVE` trong PostgreSQL.
4. Jina và frozen RQ-VAE load một lần trên CPU để index sản phẩm mới nền.

Trang chủ dùng 10 lượt xem gần nhất, giữ cả lượt lặp, rồi đi theo thứ tự:

```text
Transformer Top-10 SID
→ exact full SID
→ prefix hai tầng nếu cụm thiếu sản phẩm
→ Semantic ID gần lịch sử
→ sản phẩm phổ biến
```

Trong một cụm, sản phẩm được xếp theo số đã bán, rating và ID để kết quả ổn
định. Related products không cần Transformer: nó lùi từ full SID sang prefix
hai tầng, một tầng rồi mới dùng popularity.

Sản phẩm mới hoặc thay đổi tên/mô tả được ghi với SID rỗng. Worker chạy Jina →
RQ-VAE theo batch, cập nhật SID có điều kiện để kết quả cũ không ghi đè nội dung
seller vừa sửa, sau đó refresh mask mà không reload Transformer.

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
