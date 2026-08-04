# Tổng quan 4 paper — bản gỡ rối

> Đọc file này trước khi mở ghi chú chi tiết của từng bài.
> TIGER · GR4AD · CQ-SID · TSGR

---

## 1. Câu gỡ rối quan trọng nhất

**Phép residual quantization giống hệt nhau ở cả 4 bài**: chọn codeword gần nhất → trừ đi → lặp lại ở tầng sau.

Không hề có "4 loại RQ khác nhau". Chỉ có **2 biến thể**:

| Biến thể | Ai dùng | Khác nhau ở chỗ |
|---|---|---|
| **RQ-VAE** | TIGER, CQ-SID | Có encoder/decoder học cùng lúc với codebook |
| **RQ-KMeans** | GR4AD, TSGR | Embedding đã có sẵn, chỉ chạy k-means tuần tự trên residual |

Vậy 4 bài khác nhau ở đâu? → Ở **mọi thứ xung quanh quantizer**, không phải bản thân quantizer.

---

## 2. Khung nhìn: dây chuyền 4 trạm

Hình dung SID được sản xuất qua 4 trạm:

**[1] Vector nào đi vào** → **[2] Nén thế nào** → **[3] SID *nghĩa là gì*** → **[4] Ai tiêu thụ SID**

Mỗi paper cải tiến **một trạm khác nhau** (ô **in đậm** = đóng góp chính):

| Trạm | TIGER | GR4AD | CQ-SID | TSGR |
|---|---|---|---|---|
| **[1]** Vector đầu vào | Content thuần (Sentence-T5) | **Multimodal + hành vi tập thể** | **Thêm query intent** | Prior thống kê (không học) |
| **[2]** Quantizer | *Mượn nguyên từ SoundStream* | Chỉnh nhẹ: đổi cỡ codebook, cân bằng, hash tầng cuối | Ép tầng 1 = category | Nén **cụm** thay vì item |
| **[3]** SID nghĩa là gì | 1 SID = 1 item | 1 SID = 1 ad | **1 SID = 1 CỤM item** | **Token cuối = THỨ HẠNG** |
| **[4]** Ai tiêu thụ SID | Transformer sinh chuỗi | **LazyAR (nhanh ×2) + học theo tiền (VSL/RSPO)** | RL với reward hành vi (EG-GRPO) | **VRM re-rank sau khi sinh** |

**Nhìn hàng [2]**: không bài nào cải tiến quantizer một cách nghiêm túc. Đó chính là lý do không nên phân loại 4 bài theo "loại RQ".

---

## 3. Mỗi bài sáng tạo ở đâu

| Paper | Đóng góp thật sự |
|---|---|
| **TIGER** | Dựng cả dây chuyền lần đầu. Trạm [2] đi mượn. Giá trị = **ý tưởng dây chuyền**: đổi recommendation từ "tìm vector gần nhất" thành "sinh chuỗi token" |
| **GR4AD** | Đổ vào trạm [1] mọi thứ có thể (video, ASR, OCR, hành vi tập thể) và tối ưu trạm [4] cho chạy nhanh + ra tiền |
| **CQ-SID** | Đổi **định nghĩa** ở trạm [3] — SID không còn là tên riêng của một item mà là *tên một khu phố* |
| **TSGR** | Cũng đổi trạm [3] nhưng hướng khác — token cuối không mang nghĩa nội dung mà là *số thứ tự trong bảng xếp hạng* |

---

## 4. Bốn câu để nhớ

- **TIGER** — *đừng tìm item, hãy sinh tên nó ra.*
- **GR4AD** — *tên phải giàu thông tin, và sinh phải thật nhanh, thật ra tiền.*
- **CQ-SID** — *đặt tên cho cả khu phố thay vì từng nhà, để đỡ phải gọi tên nhiều lần.*
- **TSGR** — *chữ số cuối trong tên chính là hạng của món hàng.*

**Một câu duy nhất cho cả 4:**
> Cả 4 dùng chung một phép nén; chúng khác nhau ở chỗ **cái gì được nén**, và **cái tên nén ra ấy được hiểu là gì**.

---

## 5. Những hiểu nhầm hay gặp

| Hiểu nhầm | Thực tế |
|---|---|
| "TIGER tối ưu codeword trong RQ-VAE" | TIGER **không đụng gì** vào RQ-VAE. Mượn nguyên từ SoundStream (ref [40]), kể cả mẹo khởi tạo k-means |
| "CQ-SID tạo đa dạng cluster" | Ngược lại — CQ-SID **gom lại** để giảm số beam. Cái "đa dạng" (temperature) là của TIGER |
| "4 paper = 4 loại RQ" | Chỉ có 2 loại: RQ-VAE và RQ-KMeans |
| "Token cuối là tầng residual thứ 4" | TIGER: số thứ tự chống trùng, gán **sau khi** train xong. TSGR: vị trí xếp hạng. Không tầng nào là residual |
| "RQ-VAE tự sinh SID theo autoregressive" | RQ-VAE chỉ chọn nearest codeword. **Transformer** mới là phần autoregressive |
| "RQ-VAE và Transformer học song song" | Học **nối tiếp**: RQ-VAE xong, đóng băng, rồi mới train Transformer. Gradient không chảy ngược |
| "Collision luôn là xấu" | TIGER/GR4AD coi là kẻ thù cần khử; CQ-SID coi là **công cụ thiết kế** để gom cụm |
| "PV trong TSGR là chỉ số tiền" | PV = page view (lượt hiển thị). **CVR** mới là cái gần tiền — và ablation cho thấy nó *thừa* |
| "SID đủ để mô tả một item" | TSGR chứng minh ngược lại: bỏ item embedding thì sụt thảm hại, vì **nén thành SID làm mất nhiều thông tin** |

---

## 6. Tra nhanh thông số

| | TIGER | GR4AD | CQ-SID | TSGR |
|---|---|---|---|---|
| Nguồn | NeurIPS 2023 | Kuaishou, arXiv 2602.22732 | arXiv 2605.14434 | Taobao, arXiv 2607.18796 |
| Bài toán | Sequential recommendation | Advertising | E-commerce search recall | Search retrieval + pre-ranking |
| Encoder | Sentence-T5 (768d) → DNN (32d) | MLLM instruction-tuned | Item/Query Encoder (*không công bố*) | Không train (mean-pooling) |
| Codebook | 3 × 256 | 16384 → 4096 → 1024 | 2048 → 1024 → 1024 | 8192 × 4 × 8192 (merge 2 tầng đầu → 32768) |
| Model sinh | Transformer enc-dec ~13M | LazyAR 9 layer (K=6) | Qwen2.5-0.5B | Qwen + VRM head |
| Business value | — | VSL + RSPO (eCPM) | EG-GRPO (purchase/click 1.0, exposure 0.5, valid 0.1) | SID ordering + PV × CTR |
| Vai trò hệ thống | Retrieval nghiên cứu | Hệ generative trung tâm | Recall channel bổ sung | Retrieval + pre-ranking hợp nhất |

---

## 7. Cách 4 bài nối tiếp nhau

TIGER mở đường nhưng còn thô. Mỗi khiếm khuyết của nó về sau thành đề tài một bài khác:

| Khiếm khuyết của TIGER | Ai vá | Vá bằng cách nào |
|---|---|---|
| SID chỉ từ content, không có tín hiệu hành vi | GR4AD | Co-occurrence InfoNCE trước khi lượng tử hóa |
| Codebook collapse, utilization thấp | GR4AD (FORCE, QARM) | Balanced K-means, multi-resolution |
| One-item-one-SID → beam đắt | CQ-SID | Cluster SID: 1 SID mở ~30 item |
| Sinh xong không biết item nào đáng tiền | GR4AD, TSGR | VSL/RSPO; VRM re-rank |
| Decoding chậm khi beam lớn | GR4AD | LazyAR: 2/3 layer dùng chung mọi beam |

---

## 8. Hai bài học thực nghiệm đáng nhớ nhất

Rút từ ablation của TSGR (pool 5000 candidate) — áp dụng được cho bất kỳ hệ Semantic ID nào:

**Tín hiệu "value" phải khớp metric đang tối ưu.** TSGR có ba đầu ra PV / CTR / CVR, nhưng khi inference chỉ dùng **PV × CTR** — vì tích này tương ứng trực tiếp với mục tiêu HitRate. Bỏ hẳn CVR loss khi train thì ảnh hưởng không đáng kể. Nghĩa là: chỉ số nghe "ra tiền" nhất (chuyển đổi) lại **thừa ở tầng retrieval**; chuyện tiền nong để tầng ranking phía sau lo.

**SID là bản nén có mất mát.** Bỏ item embedding khỏi VRM → sụt mạnh cả HR@20 lẫn HR@1000. Paper thừa nhận thẳng: *quá trình xây SID chắc chắn làm mất một lượng lớn thông tin item*. Ba con số không đủ mô tả một sản phẩm.

→ Hệ quả về mặt tư tưởng: **TIGER tin SID tự nó đủ để định danh và truy xuất. TSGR chỉ dùng SID để tìm đúng vùng, rồi lôi thông tin thật ra mới chọn món cụ thể.** Hai mức độ tin tưởng rất khác nhau vào Semantic ID.

**Cùng một phép RQ, chỉ đổi cách phân bổ codebook đã đổi hẳn chất lượng SID.** Bảng ablation của GR4AD (cùng tổng không gian mã):

| Thiết kế | Collision ↓ | Utilization ↑ |
|---|---|---|
| RQ-KMeans đều nhau (4096, 4096, 4096) | 85.44% | 0.10‰ |
| + multi-resolution (16384, 4096, 1024) | 59.72% | 0.20‰ |
| + hash business ở tầng cuối = UA-SID | **18.26%** | 0.34‰ |

**Nhưng tokenization không phải nơi kiếm được nhiều nhất.** Toàn bộ tối ưu embedding + quantization của GR4AD chỉ đem lại **+0.24% doanh thu**, trong khi **RSPO** (học list-wise theo business value) là thành phần đóng góp lớn nhất. SID tốt là *nền móng cần thiết*, còn phần lớn lợi nhuận đến từ tầng objective. → Đừng dồn hết công sức vào tokenization rồi bỏ ngỏ objective.

---

## 9. Ghi chú chi tiết từng bài

- [TIGER](TIGER/TIGER_ghi_chu_research_tong_hop.docx)
- [GR4AD](GR4ND/GR4AD_ghi_chu_research_day_du_LazyAR_VSL_de_hieu.docx)
- [CQ-SID](CQ-SID/CQ-SID_ghi_chu_research_cap_nhat.docx)
- [TSGR](TSGR/TSGR_ghi_chu_research_cap_nhat.docx)

Mỗi file đều đã có mục **"0. Kiến trúc tổng thể"** ở đầu, kèm hình từ paper gốc.
