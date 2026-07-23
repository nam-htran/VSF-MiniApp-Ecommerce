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
import base64
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
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


# One live sale per shop, in shop order. The best applicable one applies
# itself to the card price and again to the order — nobody types a code.
# `days` is the window relative to today, so a reseed always lands live.
VOUCHERS = [
    # Shop 1 gets two, on purpose: one that bites straight away and one that
    # needs a big basket, so checkout shows a live code beside a greyed-out
    # one with "cần thêm …".
    [
        {
            "code": "BINHMINH25",
            "description": "Giảm 25% toàn shop, tối đa 200.000₫",
            "discountType": "PERCENT",
            "discountValue": 25,
            "maxDiscount": 200_000,
            "days": (-1, 14),
        },
        {
            "code": "BINHMINH500K",
            "description": "Giảm 500.000₫ cho đơn từ 5.000.000₫",
            "discountType": "AMOUNT",
            "discountValue": 500_000,
            "minOrder": 5_000_000,
            "days": (-1, 30),
        },
    ],
    # Category-scoped: only clothing counts towards it, and only clothing
    # gets discounted — the keyboard in the same basket earns nothing.
    [
        {
            "code": "ANNHIEN20",
            "description": "Giảm 20% hàng thời trang, tối đa 50.000₫",
            "category": "thoi-trang",
            "discountType": "PERCENT",
            "discountValue": 20,
            "maxDiscount": 50_000,
            "days": (-1, 10),
        },
    ],
    [
        {
            "code": "NHAMINH10",
            "description": "Giảm 10% đồ gia dụng, tối đa 30.000₫",
            "discountType": "PERCENT",
            "discountValue": 10,
            "maxDiscount": 30_000,
            "days": (-1, 21),
        },
    ],
]


# Category key per product name — keys match the client's CATEGORIES list.
CATEGORY_BY_NAME = {
    "Tai nghe chụp tai không dây": "am-thanh",
    "Đồng hồ thông minh": "dien-tu",
    "Bàn phím không dây": "dien-tu",
    "Loa Bluetooth chống nước": "am-thanh",
    "Máy ảnh đã qua sử dụng": "dien-tu",
    "Giày chạy bộ nam": "giay-dep",
    "Áo thun cotton trơn": "thoi-trang",
    "Balo laptop chống sốc": "phu-kien",
    "Đèn làm việc kim loại": "gia-dung",
    "Bình giữ nhiệt 500ml": "gia-dung",
}


# A banner and a logo per shop, generated as self-contained SVG data URIs
# so the seed depends on no image host or bundled asset — they render the
# same in dev, in tests, and anywhere the whitelist would block a CDN. Real
# sellers replace both with uploads.
SHOP_COLORS = [("#e11d48", "#fb7185"), ("#2563eb", "#60a5fa"), ("#0d9488", "#2dd4bf")]


def _svg_data_uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(
        svg.encode("utf-8")
    ).decode("ascii")


def _banner_uri(index: int) -> str:
    """A gradient with a few soft blobs — deliberately textless.

    The shop's name is always rendered next to the banner, so baking it in
    would show it twice, and any crop (the small card on a product page)
    would slice the baked copy in half.
    """
    c1, c2 = SHOP_COLORS[index % len(SHOP_COLORS)]
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="240">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{c1}"/>'
        f'<stop offset="1" stop-color="{c2}"/></linearGradient></defs>'
        '<rect width="600" height="240" fill="url(#g)"/>'
        '<circle cx="500" cy="40" r="110" fill="#ffffff" opacity="0.10"/>'
        '<circle cx="120" cy="210" r="90" fill="#ffffff" opacity="0.08"/>'
        '<circle cx="330" cy="120" r="60" fill="#ffffff" opacity="0.06"/>'
        "</svg>"
    )
    return _svg_data_uri(svg)


def _logo_uri(name: str, index: int) -> str:
    c1, _ = SHOP_COLORS[index % len(SHOP_COLORS)]
    letter = name.strip()[0]
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120">'
        '<rect width="120" height="120" rx="28" fill="#ffffff"/>'
        f'<rect x="8" y="8" width="104" height="104" rx="22" fill="{c1}"/>'
        '<text x="60" y="80" font-family="sans-serif" font-size="56" '
        f'font-weight="bold" fill="#ffffff" text-anchor="middle">{letter}</text>'
        "</svg>"
    )
    return _svg_data_uri(svg)


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
                "imageUrl": _banner_uri(index),
                "logoUrl": _logo_uri(shop_name, index),
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
                "category": CATEGORY_BY_NAME.get(name),
                "imageUrl": f"/src/assets/products/{image}.jpg",
            }
            if original is not None:
                payload["originalPrice"] = original
            post(BACKEND, "/products", payload, token)

        codes = []
        for template in VOUCHERS[index] if index < len(VOUCHERS) else []:
            voucher = dict(template)
            start_days, end_days = voucher.pop("days")
            now = datetime.now(timezone.utc)
            voucher["startsAt"] = (now + timedelta(days=start_days)).isoformat()
            voucher["endsAt"] = (now + timedelta(days=end_days)).isoformat()
            post(BACKEND, "/vouchers", voucher, token)
            codes.append(voucher["code"])
        suffix = f", mã {', '.join(codes)}" if codes else ""
        print(f"  {shop_name}: {len(product_rows)} sản phẩm{suffix}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(truncate())
    seed()
    total = sum(len(rows) for *_, rows in SHOPS)
    print(f"Xong: {len(SHOPS)} shop, {total} sản phẩm.")
