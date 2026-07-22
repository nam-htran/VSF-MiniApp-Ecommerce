"""Reset the database and fill it with demo shops and products.

Run it whenever the demo data is gone — most often because the test
suite truncates every table it touches.

Needs both servers up, because it seeds through the real flow:
register a V-App account on the mock, log in, open a shop, add
products. Nothing is inserted behind the API's back.

    docker compose up -d
    mock-openAPI:  uvicorn main:app --port 4001
    server:        uvicorn app.main:app --port 4000

    .venv\\Scripts\\python.exe scripts/seed_demo.py

Image paths point into the MiniApp's own dev bundle
(/src/assets/products/…), which the Vite dev server serves from the
same origin as the app — a dev-only convenience. Real products get
uploaded images once the backend can store them.
"""

import asyncio
import json
import sys
import urllib.request
from pathlib import Path

# Runnable from anywhere: put server/ on the path so `app.*` imports work.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MOCK = "http://127.0.0.1:4001"
BACKEND = "http://127.0.0.1:4000"

# (name, description, unit, price, original_price | None, stock, image)
# original_price set = the item lands in the flash-sale strip.
SHOPS = [
    (
        "Điện máy Bình Minh",
        "Tivi, tủ lạnh, máy giặt chính hãng, bảo hành 24 tháng",
        [
            ("Ức gà đông lạnh", "Cấp đông ngay sau giết mổ.", "450–500g /gói", 56000, 80000, 40, "chicken"),
            ("Trứng gà ta", "Thu hoạch trong tuần.", "Hộp 12 quả", 32500, 50000, 60, "eggs"),
            ("Thịt bò nấu súp", "Cắt khối sẵn.", "450–500g /gói", 75000, 93000, 25, "beef"),
        ],
    ),
    (
        "Tạp hoá Cô Chi",
        "Đồ khô, gia vị, hàng thiết yếu giao trong ngày",
        [
            ("Gạo ST25", "Vụ mới.", "Túi 5kg", 166500, 185000, 30, "rice"),
            ("Sốt cà chua", "Không chất bảo quản.", "Hũ 300g", 42000, 52000, 50, "sauce"),
            ("Sữa tươi nguyên chất", "Tiệt trùng.", "Chai 1 lít", 38000, None, 45, "milk"),
            ("Bánh mì nguyên cám", "Nướng mỗi sáng.", "Ổ 400g", 45000, None, 20, "bread"),
        ],
    ),
    (
        "Sách cũ Hà Nội",
        "Sách văn học và giáo trình đã qua sử dụng, giá mềm",
        [
            ("Salad rau củ tươi", "Rửa sẵn.", "Hộp 400g", 35000, None, 35, "greens"),
            ("Cá hồi phi lê", "Hàng tươi.", "200–250g /khay", 129000, 155000, 15, "salmon"),
            ("Táo đỏ nhập khẩu", "Size 70.", "Túi 1kg", 89000, None, 55, "apple"),
        ],
    ),
]


def post(base: str, path: str, payload: dict, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        base + path, data=json.dumps(payload).encode(), headers=headers
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)


async def truncate() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.config import settings

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE products, shops, users CASCADE"))
    await engine.dispose()


def seed() -> None:
    for index, (shop_name, shop_desc, product_rows) in enumerate(SHOPS):
        owner = post(MOCK, "/simulator/users", {"name": f"Chủ shop {index + 1}"})
        code = post(
            MOCK,
            "/simulator/authcode",
            {"user_id": owner["data"]["user_id"], "scopes": "profile phone"},
        )["data"]["authCode"]
        token = post(BACKEND, "/auth/session", {"authCode": code})["token"]

        post(BACKEND, "/shops", {"name": shop_name, "description": shop_desc}, token)
        for name, description, unit, price, original, stock, image in product_rows:
            payload = {
                "name": name,
                "description": description,
                "unit": unit,
                "price": price,
                "stock": stock,
                "imageUrl": f"/src/assets/products/{image}.jpg",
            }
            if original is not None:
                payload["originalPrice"] = original
            post(BACKEND, "/products", payload, token)
        print(f"  {shop_name}: {len(product_rows)} sản phẩm")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(truncate())
    seed()
    total = sum(len(rows) for _, _, rows in SHOPS)
    print(f"Xong: {len(SHOPS)} shop, {total} sản phẩm.")
