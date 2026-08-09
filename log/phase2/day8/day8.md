# Ngày 8 — Codebook, hội tụ, và ba lỗi tìm được

## Multi-resolution: tái lập được tuyên bố của GR4AD

GR4AD nói: cùng tổng không gian mã, chỉ cần **phân bổ codebook to ở tầng đầu nhỏ dần ở tầng sau** là collision tụt từ 85% xuống 18%. Thử lại với `1024 × 256 × 64` so với `256³` (cùng 16,8M ô):

| Config | Ô | Recon | Entropy | SID hiệu dụng | Tầng 1 dùng |
|---|---|---|---|---|---|
| 256³ | 16,8M | 0.1183 | 12.531 | 276.684 | 256/256 |
| 128×64×32 | 262K | 0.1459 | 10.848 | 51.441 | 128/128 |
| **1024×256×64** | 16,8M | **0.1108** | **12.980** | **433.564** | 993/1024 |

Cùng số ô như 256³ nhưng **nhiều hơn 57% SID hiệu dụng**, reconstruction tốt nhất. Tầng 1 leo đều 104 → 993/1024 qua các mốc eval. **Tuyên bố của GR4AD đúng.**

## Nhưng vẫn chọn 128×64×32

Vì bài toán là **trình bày 3 tầng** (tương tự / có thể thích / cùng ngành), không phải đoán trúng món. Kích thước cụm mới là thứ quyết định:

| Dùng | 128×64×32 | 1024×256×64 |
|---|---|---|
| Khớp 3 tầng — *"tương tự"* | trung vị **4**, p90 22 | ~3 món |
| Khớp 2 tầng — *"có thể thích"* | trung vị **105** | — |
| Khớp 1 tầng — *"cùng ngành"* | trung vị **10.664** | — |

Ba mức 4 / 105 / 10.664 đúng ba hàng của giao diện kiểu Shopee. Cụm 3 món thì quá mỏng để lấp một hàng.

Ngoài ra 1024×256×64 mịn gấp 8,4 lần (3,25 so với 27,4 sản phẩm mỗi cụm) nên cluster h@10 tụt từ 0.4734 xuống 0.3467.

## Balanced K-means: đo ra là no-op

Ý tưởng: ép mỗi centroid nhận số item gần bằng nhau → cụm đều → hàng gợi ý đều.

Chạy 2 lần có balanced, so với 1 lần không balanced:

| Chỉ số | KHÔNG bal | CÓ bal #1 | CÓ bal #2 |
|---|---|---|---|
| entropy SID | 10.848 | 10.859 ↑ | 10.824 ↓ |
| batch unique SID | 0.98311 | 0.98384 ↑ | 0.98293 ↓ |
| eval recon | 0.14587 | 0.14585 ≈ | 0.14754 ↓ |
| emb norm tầng 0 | 0.04538 | 0.04617 ↑ | 0.04474 ↓ |

Run không balanced **nằm giữa** hai run balanced ở mọi chỉ số — dấu hiệu kinh điển của nhiễu.

```
Nhiễu giữa 2 seed cùng cấu hình:  0.035 nats
Chênh giữa có/không balanced:     0.007 nats   ← nhỏ hơn 5 lần
```

Kiểm tra thẳng vào thứ nó phải sửa — phân bố kích thước cụm tầng 1:

| | CŨ | MỚI (balanced) |
|---|---|---|
| số cụm | 128 | 127 |
| nhỏ nhất | 4.475 | 3.364 |
| lớn nhất | 28.761 | 29.526 |
| **chênh max/min** | **6,43×** | **8,78×** ← tệ hơn |

Có đúng một chỗ tốt lên: cụm lớn nhất tầng 3 giảm 3.924 → 1.697. Nhưng **trung vị và p90 không đổi** (4 và 22), nên 99% hàng gợi ý y hệt nhau.

**Nguyên nhân là cấu trúc, không phải chỉnh sai tham số.** `kmeans_init_` chạy đúng **một lần ở bước 0**; sau đó 50.000 bước gradient kéo centroid đi đâu tuỳ dữ liệu. Cân bằng **không nằm trong hàm mục tiêu** nên bị xoá sạch.

Muốn cụm thật sự đều thì phải đưa áp lực cân bằng vào loss lúc train, hoặc hậu xử lý chia cụm to như CQ-SID (`Tmax = 50`).

→ Đã gỡ khỏi dự án.

## Hội tụ: 100k là chưa đủ

Run 100k nhìn qua tưởng đã xong — train loss `5.7896` (90k) → `5.7880` (99k), gần như phẳng. **Đọc vậy là sai.**

Ngoại suy từ gia số h@10 (`+0.0207 +0.0103 +0.0069 +0.0060`, tỉ lệ suy giảm ~0.85) cho tiệm cận **0.493**. Train thật 200k:

| | 100k | **200k** |
|---|---|---|
| cluster h@10 | 0.4734 | **0.4930** |
| ndcg | 0.3472 | **0.3622** |
| h@1 | 0.2346 | 0.2441 |

Dự đoán 0.493, thực tế **0.4930**. Trúng.

Chỗ "phẳng" ở 90–99k chỉ là **chững tạm thời** — run 200k cũng chững đúng chỗ đó (Δ = −0.0000) rồi giảm tiếp xuống 5.549. Tốc độ giảm nửa sau khá đều, không tắt dần:

| đoạn | Δ loss |
|---|---|
| 99k → 120k | −0.068 |
| 120k → 150k | −0.040 |
| 150k → 180k | −0.051 |
| 180k → 198k | −0.033 |

Đó là dáng điển hình của `inverse sqrt` — loss giảm theo `log(số bước)`.

**Loss và metric không cùng nhịp.** Loss vẫn xuống đều trong khi gia số h@10 cuối chỉ còn **+0.0020**. Lý do: loss là cross-entropy trung bình trên từng token (mềm), h@10 hỏi có đúng cả bộ 3 số trong beam không (cứng). Model tiếp tục sắp lại thứ tự giữa các lựa chọn suýt soát mà cross-entropy trung bình gần như không đổi.

Ngoại suy tiếp: tiệm cận ~0.504. Thêm 7 giờ để được +0.011 — không đáng.

Chạy 200k mất **7,06 giờ**, trong giới hạn 12 giờ của Kaggle.

## Ba lỗi tìm được

**1. `argsort(dim=None)` — sập ngay.** `dim=None` là API của numpy, PyTorch không nhận. Run đầu tiên chết sau **40 giây, 0 dòng log**. (Lỗi do chính hôm nay tạo ra khi viết balanced k-means, đã gỡ cùng tính năng.)

**2. Guard beam dùng `min()` thay vì tầng đầu.**

```python
- if top_k_for_generation > min(self.codebook_sizes):
+ if top_k_for_generation > self.codebook_sizes[0]:
```

Chỉ tầng 0 ràng buộc: `topk(k)` chạy trên `V` cột của codebook. Tầng sau chọn `k` trong `k*V`, không bao giờ chặn. Với TIGER mọi codebook đều 256 nên `min` = tầng đầu, không ai phát hiện. Với `128×64×32` nó khoá beam ở **32** thay vì 128 — và với multi-resolution `1024×256×64` thì khoá ở **64**, tức bóp nghẹt đúng cái recall mà tầng đầu rộng vừa mua. Đã test beam 10 / 64 / 100 / 1024 đều sinh đủ SID phân biệt, log-prob hữu hạn. **Đã sửa, giữ lại.**

**3. `x_hat[..., :-0]` là tensor rỗng.** Trong `RqVae.forward`, khi `n_cat_feats = 0` thì `x_hat[..., :-self.n_cat_feats]` trả về **rỗng** chứ không phải cả tensor, nên `l2norm` **không bao giờ được áp dụng**.

Thử bật l2norm lên thì **tệ hơn**: cosine(x̂, x) tụt 0.8948 → 0.8431 và norm thô của decoder sụp còn 0.008 — phép chuẩn hoá che mất việc magnitude sụp đổ, và ở norm đó gradient bị khuếch đại ~120 lần, dễ underflow trong fp16.

→ Giữ nguyên hành vi cũ (không chuẩn hoá). Lỗi này **chưa sửa trong code**, chỉ ghi lại ở đây.

## Trạng thái code cuối ngày

So với commit `9f84c75` đầu ngày, `ai-recommendation/src/` chỉ khác **2 file, 6 dòng**:

| File | Đổi |
|---|---|
| `modules/model.py` | sửa guard beam `min()` → `[0]` |
| `configs/transformer_vmarket.gin` | `iterations` 100000 → 200000, tên run |

Đã gỡ hết: VRM head, config `1024×256×64`, entropy regularizer, balanced k-means, mọi sửa đổi notebook 03/04.

---

## Nguồn

**Từ wandb** (`hnamt04-personal/vmarket-rqvae`, `vmarket-transformer`): bảng RQ-VAE 3 cấu hình; 3 run balanced/không; đường loss và eval của run 100k và 200k

**Đo trong ngày:** phân bố kích thước cụm theo độ sâu prefix trên `semantic_ids.parquet` (bản cũ và bản mới); thử nghiệm l2norm trên dữ liệu tổng hợp có cấu trúc; beam 10/64/100/1024 sau khi sửa guard

**Từ paper:** GR4AD — collision 85% → 18% cùng tổng không gian mã; CQ-SID — `Tmax = 50`

**Chưa kiểm chứng:** tiệm cận ~0.504 khi train quá 200k (ngoại suy từ 10 điểm eval)
