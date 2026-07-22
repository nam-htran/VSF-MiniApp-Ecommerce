# Ngày 2 — Lưu trữ: Postgres + SQLAlchemy

Tài liệu này giải thích code đã viết. Lý do chọn Postgres nằm ở [research.md](research.md).

---

## 1. Vấn đề

Ngày 1, `server/app/users/store.py` giữ người dùng trong một `dict` ở cấp module. Tắt server là mất sạch. Với luồng đăng nhập thì chấp nhận được — nhưng shop, sản phẩm, đơn hàng thì không: demo mà restart một lần là trắng dữ liệu.

Ngoài ra có một yêu cầu mà `dict` không làm được, là **INV-05** — hai người mua cùng một lúc món hàng cuối cùng, chỉ một người được. Cần `SELECT ... FOR UPDATE`, tức là cần một database thật.

---

## 2. Thêm gì

| File | |
|---|---|
| `docker-compose.yml` | **mới** — Postgres 18 chạy local |
| `server/app/db.py` | **mới** — engine, session, `Base`, `create_tables` |
| `server/app/config.py` | thêm `database_url` |
| `server/app/users/store.py` | `dict` → model SQLAlchemy |
| `server/app/auth/routes.py` | nhận `session`, các lời gọi thành `await` |
| `server/app/main.py` | `lifespan` |
| `server/requirements.txt` | `sqlalchemy[asyncio]`, `asyncpg`, `greenlet` |
| `server/tests/conftest.py` | fixture dựng và dọn DB |

---

## 3. Container

```yaml
ports:
  - "5433:5432"
volumes:
  - vmarket-db-data:/var/lib/postgresql
```

**Cổng 5433** vì 5432 thường đã có Postgres cài sẵn trên máy chiếm.

**Mount ở `/var/lib/postgresql`, không phải `/var/lib/postgresql/data`.** Từ Postgres 18, image đặt `PGDATA` vào một thư mục con để `pg_upgrade --link` không phải nhảy qua ranh giới mount. Mount đúng vào `data` theo thói quen cũ thì container khởi động rồi thoát ngay.

```bash
docker compose up -d      # bật
docker compose down -v    # xoá sạch, kể cả dữ liệu
```

---

## 4. Ba thứ trong `db.py`

```python
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)
class Base(DeclarativeBase): pass
```

| | Là gì | Có mấy cái |
|---|---|---|
| `engine` | Pool kết nối tới Postgres | **Một** cho cả tiến trình |
| `SessionFactory` | Khuôn đúc session | Một |
| `session` | Một đơn vị công việc = một transaction | **Một cho mỗi request** |

`pool_pre_ping=True`: ping trước khi lấy kết nối ra khỏi pool. Kết nối nhàn rỗi có thể đã bị Postgres hoặc firewall cắt mà pool chưa biết — không ping thì request đầu tiên sau đó lãnh lỗi.

`expire_on_commit=False`: mặc định, sau `commit()` SQLAlchemy đánh dấu mọi object là hết hạn, chạm vào thuộc tính nào là nó bắn thêm một câu `SELECT`. Trong async, lần tải lại ngầm đó ném `MissingGreenlet`. Tắt đi thì object giữ nguyên giá trị sau commit — đó là lý do `create_user` trả `user` ra được và route đọc `user.id` bình thường.

---

## 5. Session theo từng request

```python
async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session
```

`yield` chứ không `return`, để FastAPI chạy hàm này làm ba nhịp:

| Nhịp | |
|---|---|
| Trước handler | chạy tới `yield` → mở session |
| Trong handler | session được tiêm vào tham số |
| Sau khi trả response | chạy tiếp sau `yield` → `async with` thoát → đóng session |

Phần dọn dẹp chạy cả khi handler ném exception.

Bên route khai báo một lần rồi dùng lại:

```python
Session = Annotated[AsyncSession, Depends(get_session)]

async def create_shop(body: CreateShopRequest, session: Session) -> dict:
```

**Không dùng chung một session cho nhiều request.** Session mang trạng thái transaction; hai request chung một session thì `commit` của người này nuốt luôn thay đổi dang dở của người kia.

---

## 6. Bảng được tạo lúc nào

```python
@asynccontextmanager
async def lifespan(_: FastAPI):
    await create_tables()
    yield
    await engine.dispose()
```

`lifespan` là dependency của cả ứng dụng, cùng cấu trúc `yield` như §5 nhưng vòng đời là **cả tiến trình**: trước `yield` chạy lúc boot, sau `yield` chạy lúc tắt. `engine.dispose()` trả kết nối về cho Postgres thay vì để nó bị cắt ngang.

`create_tables` gọi `Base.metadata.create_all`. `Base.metadata` là sổ đăng ký — mỗi class kế thừa `Base` tự ghi tên mình vào đó **lúc được import**. Nên `main.py` phải import các module `store` dù không dùng biến nào:

```python
from app.shops import store as _shops  # noqa: F401
from app.users import store as _users  # noqa: F401
```

Thiếu dòng này thì metadata rỗng và `create_all` tạo ra... không gì cả.

> **`create_all` chỉ tạo, không bao giờ sửa.** Thêm một cột vào model rồi restart: bảng đã tồn tại nên nó bỏ qua trong im lặng, và query đầu tiên chạm cột đó báo `UndefinedColumnError`. Hiện chữa bằng `docker compose down -v`. Khi đã có dữ liệu demo đáng giữ (khoảng ngày 18) thì cần Alembic để sinh `ALTER TABLE`.

---

## 7. `dict` → bảng

```python
# Ngày 1
_by_vapp_user_id: dict[str, MarketUser] = {}

def find_by_vapp_user_id(vapp_user_id: str) -> MarketUser | None:
    return _by_vapp_user_id.get(vapp_user_id)
```

```python
# Ngày 2
class MarketUser(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(primary_key=True)
    # Unique: hai dòng cho một người sẽ chẻ đôi lịch sử đơn hàng của họ.
    vapp_user_id: Mapped[str] = mapped_column(unique=True, index=True)
    role: Mapped[str]
    seller_id: Mapped[str | None] = mapped_column(default=None)
    ...

async def find_by_vapp_user_id(session, vapp_user_id) -> MarketUser | None:
    return await session.scalar(
        select(MarketUser).where(MarketUser.vapp_user_id == vapp_user_id)
    )
```

Chữ ký hàm đổi: thành `async`, và mọc thêm tham số `session`. Đó là toàn bộ thay đổi bên `auth/routes.py` — thêm `Depends(get_session)` và `await`.

`unique=True` trên `vapp_user_id` là **ràng buộc ở tầng DB, không phải ở code**. Một `if` trong Python thua hai request đồng thời: cả hai cùng đọc thấy "chưa có" rồi cùng ghi. Ràng buộc DB thì không lách được — request thua nhận `IntegrityError`.

`reset()` bị xoá; việc dọn dữ liệu chuyển sang tầng test.

---

## 8. Test

Ba điểm trong `conftest.py`.

**Engine riêng cho test:**

```python
def _throwaway_engine():
    return create_async_engine(settings.database_url, poolclass=NullPool)
```

Test chạy trên event loop của pytest, còn app chạy trong thread uvicorn với event loop của nó. **Pool asyncpg không dùng được từ hai loop.** Nên test tự tạo engine `NullPool` (không giữ pool), xong thì `dispose` ngay.

**Dọn bằng TRUNCATE, không phải rollback:**

```python
await conn.execute(text("TRUNCATE TABLE shops, users CASCADE"))
```

Thủ thuật "mở transaction rồi rollback sau mỗi test" chỉ chạy khi test và app dùng chung session. Ở đây app ở thread khác với session riêng, nên phải xoá thật. `CASCADE` vì `shops` tham chiếu `users`.

**Fixture DB không `autouse`:**

`test_contract.py` chỉ kiểm hợp đồng giữa gateway và `mock-openAPI`, không chạm DB. Nếu bắt buộc phải có Postgres thì 8 ca đó tự nhiên hỏng khi không bật Docker. Chỉ `test_auth_flow.py` và `test_shops.py` tự đăng ký:

```python
@pytest_asyncio.fixture(autouse=True)
async def _empty(clean_db):
    yield
```

Không có DB thì chúng bỏ qua kèm hướng dẫn `docker compose up -d`, phần còn lại vẫn chạy.

---

## 9. Chạy

```bash
docker compose up -d

cd server
.venv\Scripts\python.exe -m uvicorn app.main:app --port 4000 --reload
.venv\Scripts\python.exe -m pytest
```

Kết nối mặc định trong `server/.env`:

```
DATABASE_URL=postgresql+asyncpg://vmarket:vmarket@127.0.0.1:5433/vmarket
```

`+asyncpg` là driver. Bỏ đi thì SQLAlchemy dùng driver đồng bộ và `create_async_engine` báo lỗi.

---

Phần quản lý shop (`app/shops/`, `app/auth/deps.py`) thuộc ngày 3, tài liệu ở `docs/day3/`.
