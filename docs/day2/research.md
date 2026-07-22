# Ngày 2 — Research: tầng lưu trữ

## V-App có quy định database không?

**Không.** Crawl toàn bộ `developer.v-app.vn` (193 trang) — không trang nào nói backend MiniApp phải dùng DB gì. Chữ "Database" xuất hiện đúng một lần, trong sơ đồ kiến trúc nội bộ của COV.

V-App chỉ quan tâm hợp đồng HTTP. Nên chọn DB là **quyết định của mình**, cần tự biện minh.

## Sản phẩm lớn dựng DB ở đâu

| Mô hình | Ví dụ | Ai dùng |
|---|---|---|
| Managed cloud | AWS RDS/Aurora, Google Cloud SQL, Azure Database for PostgreSQL | Đa số — nhà cung cấp lo backup, failover, vá lỗi |
| Serverless Postgres | Neon, Supabase, PlanetScale, CockroachDB Cloud | Startup, sản phẩm mới — tự co giãn |
| Tự vận hành | Postgres/Oracle trên VM hoặc K8s, on-premise | Doanh nghiệp lớn có đội DBA, hoặc bị ràng buộc pháp lý |

**VSF nhiều khả năng thuộc nhóm ba** — tài liệu V-App nhắc SAP, MuleSoft, Payment Hub, COV, đều là dấu hiệu hạ tầng nội bộ. *(Suy luận, tài liệu không nói.)*

Hai văn bản pháp lý hay bị gộp nhầm:

| Văn bản | Nội dung |
|---|---|
| **NĐ 53/2022/NĐ-CP** | Hướng dẫn Luật An ninh mạng — yêu cầu **lưu trữ dữ liệu trong nước** với một số doanh nghiệp/dịch vụ |
| **NĐ 13/2023/NĐ-CP** | Bảo vệ dữ liệu cá nhân — sự đồng ý, quyền chủ thể, **thủ tục** khi chuyển dữ liệu ra nước ngoài (không cấm) |

## Nguyên tắc ở quy mô lớn

**DB ở tầng riêng, mạng riêng** — không cùng máy với app, không mở ra internet.

**Primary + read replica** — ghi một chỗ, đọc chia nhiều chỗ. Lưu ý: PITR chỉ chạy trên primary, không chạy trên replica.

**Connection pooling** — Postgres tạo **một OS process cho mỗi kết nối**, tốn ~5–10 MB. Tới 500 kết nối là 500 process và bộ lập lịch của OS thành nút thắt. PgBouncer gom 500 kết nối ứng dụng xuống còn ~20 kết nối thật. RDS Proxy làm sẵn việc này.

**Backup + PITR** — RDS đẩy transaction log lên S3 mỗi 5 phút, cho phép khôi phục về đúng một thời điểm trong khoảng lưu 1–35 ngày, không chỉ snapshot đêm qua.

## Tách kho theo loại việc

Tên chính thức của pattern này là **polyglot persistence** — AWS Well-Architected xếp vào `PERF03-BP01`.

| Việc | Ở đâu | Vì sao |
|---|---|---|
| Đơn hàng, tồn kho, thanh toán | Postgres/MySQL | Cần transaction, cần đúng tuyệt đối |
| Tìm kiếm sản phẩm | Elasticsearch | Postgres full-text kém, và search làm nặng DB chính |
| Giỏ hàng, session | Redis | Đọc/ghi liên tục, mất cũng không chết ai |
| Báo cáo, phân tích | BigQuery/Snowflake | Query báo cáo chạy trên DB chính làm chậm khách đang mua |

Nguyên tắc: **giữ DB giao dịch nhỏ và nhanh**, mọi thứ khác đẩy sang kho riêng. AWS diễn đạt là chọn kho theo *access pattern*, không theo thứ mình quen dùng.

---

## Nguồn

**Kiểm chứng trong dự án:**
- V-App không quy định database — crawl 193 trang `developer.v-app.vn`
- SAP / MuleSoft / Payment Hub / COV — `backend-api/resources/orders/`, `.../payment/*`

**Pháp lý:**
- [Nghị định 13/2023/NĐ-CP — toàn văn](https://vanban.chinhphu.vn/?pageid=27160&docid=207759)
- [KPMG — phân tích Nghị định 13](https://kpmg.com/vn/vi/home/phan-tich-chuyen-sau/2023/04/nghi-dinh-13-ve-bao-ve-du-lieu-ca-nhan.html)

**Kiến trúc:**
- [AWS Well-Architected — PERF03-BP01: Use a purpose-built data store](https://docs.aws.amazon.com/wellarchitected/latest/framework/perf_data_use_purpose_built_data_store.html)
- [AWS — Polyglot Persistence](https://docs.aws.amazon.com/whitepapers/latest/modern-application-development-on-aws/polyglot-persistence.html)
- [AWS — Choosing an AWS database service](https://docs.aws.amazon.com/databases-on-aws-how-to-choose/)
- [ScaleGrid — PostgreSQL Connection Pooling: PgBouncer](https://scalegrid.io/blog/postgresql-connection-pooling-part-2-pgbouncer/)
- [Akamai — PgBouncer for managed PostgreSQL](https://www.akamai.com/blog/performance/pgbouncer-connection-pooling-managed-postgresql-databases)
- [AWS RDS — Read replicas for PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_PostgreSQL.Replication.ReadReplicas.html)
- [AWS Backup — Continuous backups and PITR](https://docs.aws.amazon.com/aws-backup/latest/devguide/point-in-time-recovery.html)

**Chưa dẫn nguồn:** ba mô hình hosting ở bảng đầu, và suy luận VSF thuộc nhóm tự vận hành.
