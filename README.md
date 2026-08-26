# V-Market

V-Market là sàn thương mại điện tử nhiều người bán chạy dưới dạng V Mini App.
Dự án kết hợp luồng mua bán hoàn chỉnh với hệ gợi ý sinh dựa trên Semantic ID:
RQ-VAE gom sản phẩm vào các cụm phân cấp, Transformer dự đoán cụm tiếp theo từ
lịch sử xem, còn FastAPI chọn sản phẩm đang hoạt động để trả về giao diện.

<p align="center">
  <img src="docs/phase2/TIGER/Architecture_RQ-VAE.png" alt="Residual Quantization V-Market" width="900" />
</p>

| Thành phần | Vai trò |
|---|---|
| [v-market](v-market/README.md) | React 19, `@v-miniapp/ui-react` và V MiniApp CLI |
| [server](server/README.md) | FastAPI, PostgreSQL, thương mại điện tử và AI serving |
| [ai-recommendation](ai-recommendation/README.md) | Jina embedding, RQ-VAE, Transformer và checkpoint |
| [mock-openAPI](mock-openAPI/README.md) | V-App Open API và payment gateway dùng cho local demo |

## Chạy local

Cần Docker, Node.js 22+, pnpm và Python 3.12+. Máy có NVIDIA GPU nên dùng
driver hỗ trợ CUDA 12.6; backend sẽ tự dùng CUDA cho Transformer.

```bash
git clone https://github.com/nam-htran/VSF-MiniApp-Ecommerce.git
cd VSF-MiniApp-Ecommerce

cp server/.env.example server/.env
cp mock-openAPI/.env.example mock-openAPI/.env
cp v-market/.env.example v-market/.env

cd v-market
pnpm install
pnpm dev
```

`pnpm dev` khởi động PostgreSQL, chạy migration, mở mock V-App ở cổng `4001`,
FastAPI ở `4000`, seed catalog nếu database rỗng, rồi mở V MiniApp Simulator ở
cổng `3000`.

Artifact AI được phát hiện tự động khi đặt đúng vị trí:

```text
ai-recommendation/output/rq-vae/checkpoint_49999.pt
ai-recommendation/output/rq-vae/semantic_ids.parquet
ai-recommendation/output/transformer/best_checkpoint.pt
```

Lần đầu dùng venv đã tồn tại, cài dependency CUDA trước khi chạy toàn bộ stack:

```bash
server/.venv/bin/python -m pip install -r server/requirements.txt
```
