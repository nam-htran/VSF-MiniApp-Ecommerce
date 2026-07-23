"""Reset the database and fill it with a demo marketplace.

Six shops, thirty products from scripts/demo_catalogue.json (built by
build_catalogue.py — real brands, real photos, prices in đồng), live
vouchers, size and colour options where they make sense, and reviews.

Reviews are the part that takes the work. A review is purchase-gated on the
server, so the seed cannot insert one: each demo buyer registers, places an
order, pays it through the mock gateway's IPN, and only then may rate what
they bought. That is also why "đã bán" and the star averages are real —
both are computed from paid orders.

Run it whenever the demo data is gone — most often because the test suite
truncates every table it touches.

    docker compose up -d
    mock-openAPI:  uvicorn main:app --port 4001
    server:        uvicorn app.main:app --port 4000

    .venv\\Scripts\\python.exe scripts/seed_demo.py
"""

import asyncio
import base64
import json
import random
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MOCK = "http://127.0.0.1:4001"
BACKEND = "http://127.0.0.1:4000"
CATALOGUE = Path(__file__).resolve().parent / "demo_catalogue.json"

# Same data every run, so a reseed doesn't quietly change the numbers the
# screenshots were taken against.
random.seed(20260723)

# (name, description, province, address, phone, categories it sells)
SHOPS = [
    (
        "Tech Center Bình Minh",
        "Laptop, điện thoại, máy tính bảng chính hãng — bảo hành 12 tháng",
        "Thành phố Hồ Chí Minh",
        "45 Cách Mạng Tháng 8, P.6, Quận 3",
        "0902 111 222",
        ["dien-tu"],
    ),
    (
        "Thời trang An Nhiên",
        "Quần áo nam nữ — đổi size miễn phí trong 7 ngày",
        "Thành phố Hà Nội",
        "88 Trần Duy Hưng, P. Trung Hoà, Q. Cầu Giấy",
        "0903 333 444",
        ["thoi-trang"],
    ),
    (
        "Giày Việt Sport",
        "Giày nam nữ chính hãng, có sẵn size lớn",
        "Tỉnh Bình Dương",
        "175 Đại lộ Bình Dương, P. Phú Hoà, TP. Thủ Dầu Một",
        "0907 222 333",
        ["giay-dep"],
    ),
    (
        "Phụ kiện Số 1",
        "Túi xách, đồng hồ, kính mát và phụ kiện công nghệ",
        "Thành phố Hà Nội",
        "56 Chùa Bộc, P. Quang Trung, Q. Đống Đa",
        "0908 444 555",
        ["phu-kien"],
    ),
    (
        "Gia dụng Nhà Mình",
        "Đồ bếp và đồ dùng nhà cửa, giao nhanh nội thành",
        "Thành phố Đà Nẵng",
        "12 Lê Duẩn, P. Thạch Thang, Q. Hải Châu",
        "0905 555 666",
        ["gia-dung"],
    ),
    (
        "Kho Tổng Sài Gòn",
        "Hàng tổng hợp, giá sỉ, giao toàn quốc",
        "Thành phố Cần Thơ",
        "31 Đại lộ Hoà Bình, P. Tân An, Q. Ninh Kiều",
        "0909 666 777",
        [],  # takes whatever the others don't
    ),
]

VOUCHERS = [
    [
        {
            "code": "TECH25",
            "description": "Giảm 25% toàn shop, tối đa 2.000.000₫",
            "discountType": "PERCENT",
            "discountValue": 25,
            "maxDiscount": 2_000_000,
            "days": (-1, 14),
        },
        # Deliberately out of reach for a small basket, so checkout shows a
        # live code beside a greyed-out one with "cần thêm …".
        {
            "code": "TECH5TRIEU",
            "description": "Giảm 5.000.000₫ cho đơn từ 60.000.000₫",
            "discountType": "AMOUNT",
            "discountValue": 5_000_000,
            "minOrder": 60_000_000,
            "days": (-1, 30),
        },
    ],
    [
        {
            "code": "ANNHIEN20",
            "description": "Giảm 20% hàng thời trang, tối đa 200.000₫",
            "category": "thoi-trang",
            "discountType": "PERCENT",
            "discountValue": 20,
            "maxDiscount": 200_000,
            "days": (-1, 10),
        }
    ],
    [
        {
            "code": "VIETSPORT15",
            "description": "Giảm 15% giày dép, tối đa 300.000₫",
            "category": "giay-dep",
            "discountType": "PERCENT",
            "discountValue": 15,
            "maxDiscount": 300_000,
            "days": (-1, 20),
        }
    ],
    [
        {
            "code": "PHUKIEN100K",
            "description": "Giảm 100.000₫ cho đơn từ 800.000₫",
            "discountType": "AMOUNT",
            "discountValue": 100_000,
            "minOrder": 800_000,
            "days": (-1, 16),
        }
    ],
    [
        {
            "code": "NHAMINH12",
            "description": "Giảm 12% đồ gia dụng, tối đa 150.000₫",
            "discountType": "PERCENT",
            "discountValue": 12,
            "maxDiscount": 150_000,
            "days": (-1, 25),
        }
    ],
    [
        {
            "code": "KHOTONG50K",
            "description": "Giảm 50.000₫ cho đơn từ 500.000₫",
            "discountType": "AMOUNT",
            "discountValue": 50_000,
            "minOrder": 500_000,
            "days": (-1, 18),
        }
    ],
]

# Options are per category, and only where a shop would really offer them:
# a laptop has no size, a shirt has nothing else.
SIZES_CLOTHES = ["S", "M", "L", "XL", "2XL"]
SIZES_SHOES = ["39", "40", "41", "42", "43"]
COLOURS = ["Đen", "Trắng", "Xám", "Xanh navy"]

BUYER_NAMES = [
    "Nguyễn Minh Anh", "Trần Quốc Bảo", "Lê Thu Hà", "Phạm Đức Duy",
    "Hoàng Thị Lan", "Vũ Nhật Nam", "Đặng Kim Ngân", "Bùi Thanh Tùng",
    "Đỗ Mai Phương", "Ngô Gia Huy", "Dương Khánh Linh", "Lý Trọng Nghĩa",
    "Phan Thuỳ Dung", "Trịnh Văn Sơn", "Cao Bích Ngọc", "Hồ Anh Khoa",
]

# Real reviews are mostly good and mostly short. A wall of five-star raves
# reads as fake, so the spread leans positive without being unanimous.
COMMENTS = {
    5: [
        "Hàng đẹp, đúng như mô tả. Giao nhanh hơn dự kiến.",
        "Chất lượng tốt hơn giá tiền. Sẽ ủng hộ shop tiếp.",
        "Đóng gói kỹ, sản phẩm không một vết xước. Rất hài lòng.",
        "Dùng được một tuần rồi, mọi thứ ổn. Shop tư vấn nhiệt tình.",
        "Giống hình, chắc chắn. Bạn bè hỏi mua ở đâu suốt.",
        "Mua lần hai rồi, vẫn giữ chất lượng như lần đầu.",
    ],
    4: [
        "Sản phẩm ổn trong tầm giá, đóng gói cẩn thận.",
        "Dùng tốt, chỉ là màu hơi khác hình một chút.",
        "Hài lòng. Giao hơi lâu nhưng shop có báo trước.",
        "Chất lượng ổn, giá hợp lý. Trừ một sao vì hộp hơi móp.",
        "Đúng mô tả, hoàn thiện khá. Sẽ cân nhắc mua thêm.",
    ],
    3: [
        "Tạm ổn so với giá. Không có gì đặc biệt.",
        "Hàng dùng được nhưng giao chậm mất mấy hôm.",
        "Bình thường, đúng tiền nào của nấy.",
        "Sản phẩm ổn, nhưng hướng dẫn sử dụng sơ sài quá.",
    ],
    2: [
        "Không giống hình lắm, chất liệu mỏng hơn mình nghĩ.",
        "Dùng được nhưng hoàn thiện chưa kỹ, có vài chi tiết lỏng.",
    ],
    1: ["Nhận hàng bị lỗi, liên hệ shop đổi khá lâu."],
}

RATING_WEIGHTS = [(5, 55), (4, 27), (3, 11), (2, 5), (1, 2)]
_RATING_POOL = [value for value, weight in RATING_WEIGHTS for _ in range(weight)]

SHOP_COLORS = [
    ("#e11d48", "#fb7185"), ("#2563eb", "#60a5fa"), ("#0d9488", "#2dd4bf"),
    ("#7c3aed", "#a78bfa"), ("#ea580c", "#fb923c"), ("#0891b2", "#22d3ee"),
]


def _svg_data_uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(
        svg.encode("utf-8")
    ).decode("ascii")


def _banner_uri(index: int) -> str:
    """A gradient with soft blobs — deliberately textless, because the shop
    name is always drawn next to the banner and a crop would slice a baked
    copy in half."""
    c1, c2 = SHOP_COLORS[index % len(SHOP_COLORS)]
    return _svg_data_uri(
        '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="240">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{c1}"/>'
        f'<stop offset="1" stop-color="{c2}"/></linearGradient></defs>'
        '<rect width="600" height="240" fill="url(#g)"/>'
        '<circle cx="500" cy="40" r="110" fill="#ffffff" opacity="0.10"/>'
        '<circle cx="120" cy="210" r="90" fill="#ffffff" opacity="0.08"/>'
        '<circle cx="330" cy="120" r="60" fill="#ffffff" opacity="0.06"/></svg>'
    )


def _logo_uri(name: str, index: int) -> str:
    c1, _ = SHOP_COLORS[index % len(SHOP_COLORS)]
    return _svg_data_uri(
        '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120">'
        '<rect width="120" height="120" rx="28" fill="#ffffff"/>'
        f'<rect x="8" y="8" width="104" height="104" rx="22" fill="{c1}"/>'
        '<text x="60" y="80" font-family="sans-serif" font-size="56" '
        f'font-weight="bold" fill="#ffffff" text-anchor="middle">'
        f"{name.strip()[0]}</text></svg>"
    )


def call(base, path, payload=None, token=None, method=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        base + path, data=data, headers=headers, method=method
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def token_for(name: str) -> str:
    user = call(MOCK, "/simulator/users", {"name": name})["data"]["user_id"]
    code = call(
        MOCK, "/simulator/authcode", {"user_id": user, "scopes": "profile phone"}
    )["data"]["authCode"]
    return call(BACKEND, "/auth/session", {"authCode": code})["token"]


def variants_for(entry: dict, total_stock: int) -> list[dict] | None:
    """Size or colour options, but only where a shop would really offer them.

    Each option carries its own quantity, and the product's displayed stock
    becomes their sum — once variants exist the product-level number is
    ignored entirely. The quantities are generous on purpose: splitting the
    source stock across five sizes left some with one unit, and sixteen demo
    buyers then collided on it, failing whole orders (checkout is
    all-or-nothing by design).
    """
    category = entry["category"]
    if category == "thoi-trang":
        values, group = SIZES_CLOTHES, "Size"
    elif category == "giay-dep":
        values, group = SIZES_SHOES, "Size"
    elif category == "phu-kien" and "Túi xách" in entry["name"]:
        values, group = COLOURS, "Màu sắc"
    else:
        return None

    return [
        {"options": {group: value}, "stock": random.randint(18, 45)}
        for value in values
    ]


async def truncate() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.config import settings

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE products, shops, users CASCADE"))
    await engine.dispose()


def seed_shops() -> list[dict]:
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))

    # Hand each shop the categories it sells; the last shop sweeps up
    # whatever is left so nothing in the catalogue goes unlisted.
    claimed = {c for _, _, _, _, _, cats in SHOPS for c in cats}
    buckets: list[list[dict]] = []
    for *_, cats in SHOPS:
        if cats:
            buckets.append([e for e in catalogue if e["category"] in cats])
        else:
            buckets.append([e for e in catalogue if e["category"] not in claimed])

    listed: list[dict] = []
    for index, (name, desc, province, address, phone, _) in enumerate(SHOPS):
        token = token_for(f"Chủ shop {index + 1}")
        call(
            BACKEND,
            "/shops",
            {
                "name": name,
                "description": desc,
                "province": province,
                "address": address,
                "phone": phone,
                "imageUrl": _banner_uri(index),
                "logoUrl": _logo_uri(name, index),
            },
            token,
        )

        for entry in buckets[index]:
            payload = {
                "name": entry["name"][:200],
                "description": entry["description"],
                "unit": entry["unit"],
                "price": entry["price"],
                "stock": entry["stock"],
                "category": entry["category"],
                "imageUrl": entry["images"][0] if entry["images"] else None,
                "imageUrls": entry["images"] or None,
            }
            if entry["originalPrice"]:
                payload["originalPrice"] = entry["originalPrice"]

            options = variants_for(entry, entry["stock"])
            if options:
                payload["variants"] = options

            created = call(BACKEND, "/products", payload, token)
            listed.append(
                {
                    "id": created["id"],
                    "name": created["name"],
                    "variants": [v["id"] for v in created.get("variants", [])],
                }
            )

        codes = []
        for template in VOUCHERS[index] if index < len(VOUCHERS) else []:
            voucher = dict(template)
            start_days, end_days = voucher.pop("days")
            now = datetime.now(timezone.utc)
            voucher["startsAt"] = (now + timedelta(days=start_days)).isoformat()
            voucher["endsAt"] = (now + timedelta(days=end_days)).isoformat()
            call(BACKEND, "/vouchers", voucher, token)
            codes.append(voucher["code"])

        with_options = sum(1 for e in buckets[index] if variants_for(e, 1))
        extra = f", {with_options} món có phân loại" if with_options else ""
        print(
            f"  {name}: {len(buckets[index])} sản phẩm{extra}"
            f"{', mã ' + ', '.join(codes) if codes else ''}"
        )

    return listed


def seed_reviews(listed: list[dict]) -> int:
    """Buy, pay, then rate — the only order the server permits."""
    written = 0
    for name in BUYER_NAMES:
        token = token_for(name)
        basket = random.sample(listed, random.randint(6, 11))

        # Checkout is all-or-nothing, so one sold-out line kills the basket.
        # That is correct behaviour, not a seed bug — skip the buyer and
        # carry on rather than aborting the whole run.
        try:
            order = call(
                BACKEND,
                "/orders",
                {
                    "address": (
                        f"{random.randint(1, 250)} Nguyễn Trãi, P. Bến Thành, "
                        "Quận 1, Thành phố Hồ Chí Minh"
                    ),
                    "items": [
                        {
                            "productId": item["id"],
                            # A product with options must be bought as one of
                            # them; the server refuses the line otherwise.
                            "variantId": (
                                random.choice(item["variants"])
                                if item["variants"]
                                else None
                            ),
                            "qty": 1,
                        }
                        for item in basket
                    ],
                },
                token,
            )
        except urllib.error.HTTPError as error:
            if error.code != 409:
                raise
            print(f"  bỏ qua {name}: giỏ có món đã hết hàng")
            continue

        payment = call(
            MOCK,
            "/simulator/payment/init",
            {"orderId": order["id"], "amount": int(order["total"])},
        )["data"]
        call(MOCK, f"/simulator/payment/{payment['paymentId']}/confirm", {})

        for item in random.sample(basket, k=max(int(len(basket) * 0.75), 1)):
            rating = random.choice(_RATING_POOL)
            try:
                call(
                    BACKEND,
                    f"/products/{item['id']}/reviews",
                    {"rating": rating, "comment": random.choice(COMMENTS[rating])},
                    token,
                )
                written += 1
            except urllib.error.HTTPError as error:
                # One review per buyer per product; a repeat is harmless.
                if error.code not in (403, 409):
                    raise
    return written


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if not CATALOGUE.exists():
        sys.exit("Thiếu demo_catalogue.json — chạy scripts/build_catalogue.py trước.")

    asyncio.run(truncate())
    listed = seed_shops()
    print(f"\nĐang tạo đơn và đánh giá cho {len(BUYER_NAMES)} người mua…")
    reviews = seed_reviews(listed)
    print(
        f"\nXong: {len(SHOPS)} shop, {len(listed)} sản phẩm, "
        f"{len(BUYER_NAMES)} đơn đã thanh toán, {reviews} đánh giá."
    )
