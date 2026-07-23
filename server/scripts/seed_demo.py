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
        "Thiết bị điện tử, âm thanh chính hãng, bảo hành 12 tháng",
        "Thành phố Hồ Chí Minh",
        "45 Cách Mạng Tháng 8, P.6, Quận 3",
        "0902 111 222",
        [
            ("Tai nghe chụp tai không dây", "Chống ồn chủ động, kết nối 2 thiết bị.", "Pin 30 giờ", 890000, 1290000, 25, "headphones"),
            ("Đồng hồ thông minh", "Theo dõi nhịp tim, chống nước 5ATM.", "Dây silicone", 990000, 1490000, 30, "watch"),
            ("Bàn phím không dây", "Gõ êm, kết nối 3 thiết bị.", "Bluetooth, pin sạc", 690000, 850000, 40, "keyboard"),
            ("Loa Bluetooth chống nước", "IPX7, pin 12 giờ.", "Công suất 20W", 1290000, 1690000, 20, "speaker"),
            ("Máy ảnh đã qua sử dụng", "Ngoại hình 95%, đủ phụ kiện.", "Kèm 2 ống kính", 6490000, None, 3, "camera"),
        ],
    ),
    (
        "Thời trang An Nhiên",
        "Quần áo, giày và phụ kiện — đổi size trong 7 ngày",
        "Thành phố Hà Nội",
        "88 Trần Duy Hưng, P. Trung Hoà, Q. Cầu Giấy",
        "0903 333 444",
        [
            ("Giày chạy bộ nam", "Đế đàn hồi, thoáng khí.", "Size 39–44", 1150000, 1590000, 50, "sneakers"),
            ("Áo thun cotton trơn", "100% cotton, form regular.", "Size S–XXL", 129000, None, 200, "tshirt"),
            ("Balo laptop chống sốc", "Kháng nước, cổng sạc USB.", "Ngăn 15.6 inch", 450000, 590000, 35, "backpack"),
        ],
    ),
    (
        "Gia dụng Nhà Mình",
        "Đồ dùng nhà cửa thiết yếu, giao nhanh nội thành",
        "Thành phố Đà Nẵng",
        "12 Lê Duẩn, P. Thạch Thang, Q. Hải Châu",
        "0905 555 666",
        [
            ("Đèn làm việc kim loại", "Tay đèn xoay 180°.", "Bóng E27, dây 1.8m", 350000, None, 45, "lamp"),
            ("Bình giữ nhiệt 500ml", "Giữ nóng 12h, giữ lạnh 24h.", "Inox 304", 220000, 280000, 80, "bottle"),
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
    for index, (
        shop_name,
        shop_desc,
        province,
        address,
        phone,
        product_rows,
    ) in enumerate(SHOPS):
        owner = post(MOCK, "/simulator/users", {"name": f"Chủ shop {index + 1}"})
        code = post(
            MOCK,
            "/simulator/authcode",
            {"user_id": owner["data"]["user_id"], "scopes": "profile phone"},
        )["data"]["authCode"]
        token = post(BACKEND, "/auth/session", {"authCode": code})["token"]

        post(
            BACKEND,
            "/shops",
            {
                "name": shop_name,
                "description": shop_desc,
                "province": province,
                "address": address,
                "phone": phone,
            },
            token,
        )
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
    total = sum(len(rows) for *_, rows in SHOPS)
    print(f"Xong: {len(SHOPS)} shop, {total} sản phẩm.")
