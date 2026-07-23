"""Build the demo catalogue from DummyJSON, in Vietnamese đồng.

DummyJSON is a fake-data API published for prototyping, so the catalogue
here is demo data by design rather than someone's real listings. What it
gives us is what hand-written seed data never had: real brand names, real
model numbers, sane stock levels, and several photographs per item.

Two things are deliberately not left as they came:

  * Prices are USD. They are converted and rounded to a believable đồng
    figure — 9.99 becomes 259.000₫, not 259.740₫.
  * Images are downloaded into the MiniApp's own assets. Hotlinking
    cdn.dummyjson.com would work in the Simulator and then fail in
    production, where the domain whitelist blocks anything not ours.

Writes scripts/demo_catalogue.json, which seed_demo.py reads. Re-run it
only when the catalogue should change; the seed itself needs no network
beyond the local stack.

    .venv\\Scripts\\python.exe scripts/build_catalogue.py
"""

import json
import sys
import urllib.request
from pathlib import Path

API = "https://dummyjson.com/products"
ASSETS = Path(__file__).resolve().parents[2] / "v-market/src/assets/products"
OUT = Path(__file__).resolve().parent / "demo_catalogue.json"

# Roughly the mid-market rate, rounded to a flat number. The point is a
# plausible đồng price, not an accurate one.
VND_PER_USD = 26_000

# DummyJSON category -> (our category key, Vietnamese title prefix).
# The prefix is how Vietnamese listings actually read: a Vietnamese noun in
# front, the brand and model left in English.
CATEGORIES = {
    "laptops": ("dien-tu", "Laptop"),
    "smartphones": ("dien-tu", "Điện thoại"),
    "tablets": ("dien-tu", "Máy tính bảng"),
    "mobile-accessories": ("phu-kien", "Phụ kiện"),
    "mens-watches": ("phu-kien", "Đồng hồ nam"),
    "womens-watches": ("phu-kien", "Đồng hồ nữ"),
    "womens-bags": ("phu-kien", "Túi xách"),
    "sunglasses": ("phu-kien", "Kính mát"),
    "mens-shirts": ("thoi-trang", "Áo nam"),
    "tops": ("thoi-trang", "Áo nữ"),
    "womens-dresses": ("thoi-trang", "Đầm nữ"),
    "mens-shoes": ("giay-dep", "Giày nam"),
    "womens-shoes": ("giay-dep", "Giày nữ"),
    "kitchen-accessories": ("gia-dung", "Đồ bếp"),
    "home-decoration": ("gia-dung", "Trang trí nhà"),
    "furniture": ("gia-dung", "Nội thất"),
}

# How many to take from each, adding up to thirty across all six of our
# categories rather than thirty laptops.
QUOTA = {
    "laptops": 3,
    "smartphones": 3,
    "tablets": 2,
    "mobile-accessories": 3,
    "mens-watches": 2,
    "womens-watches": 1,
    "womens-bags": 2,
    "sunglasses": 2,
    "mens-shirts": 2,
    "tops": 2,
    "womens-dresses": 1,
    "mens-shoes": 2,
    "womens-shoes": 1,
    "kitchen-accessories": 2,
    "home-decoration": 1,
    "furniture": 1,
}

UA = "VMarketDemo/1.0 (student demo)"


def to_vnd(usd: float) -> int:
    """USD -> đồng, rounded to the nearest 1.000 so prices read naturally."""
    return int(round(usd * VND_PER_USD / 1000.0)) * 1000


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def describe(item: dict, prefix: str) -> str:
    """A Vietnamese description carrying the item's real details."""
    bits = []
    if item.get("brand"):
        bits.append(f"Thương hiệu {item['brand']}.")
    bits.append(f"{prefix} chính hãng, nguyên hộp, bảo hành 12 tháng.")
    if item.get("warrantyInformation"):
        bits.append(str(item["warrantyInformation"]).rstrip(".") + ".")
    if item.get("shippingInformation"):
        bits.append(str(item["shippingInformation"]).rstrip(".") + ".")
    bits.append("Đổi trả trong 7 ngày nếu lỗi nhà sản xuất.")
    return " ".join(bits)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ASSETS.mkdir(parents=True, exist_ok=True)

    raw = json.loads(fetch(f"{API}?limit=0"))["products"]
    by_category: dict[str, list[dict]] = {}
    for item in raw:
        by_category.setdefault(item["category"], []).append(item)

    catalogue = []
    for source, take in QUOTA.items():
        our_category, prefix = CATEGORIES[source]
        for item in by_category.get(source, [])[:take]:
            slug = f"dj{item['id']:03d}"

            # Two photos where the source has them; the gallery is what the
            # detail page swipes through.
            files = []
            for index, url in enumerate(item.get("images", [])[:2]):
                suffix = "ab"[index]
                extension = ".webp" if url.endswith(".webp") else ".jpg"
                name = f"{slug}{suffix}{extension}"
                try:
                    data = fetch(url)
                except Exception as error:  # noqa: BLE001
                    print(f"  ảnh lỗi {name}: {error}")
                    continue
                if len(data) < 2000:
                    continue
                (ASSETS / name).write_bytes(data)
                files.append(f"/src/assets/products/{name}")

            price = to_vnd(item["price"])
            entry = {
                "name": f"{prefix} {item['title']}",
                "description": describe(item, prefix),
                "unit": item.get("brand") or None,
                "price": price,
                # DummyJSON's own discount, turned into a struck-through
                # original so some items land in the flash-sale strip.
                "originalPrice": (
                    to_vnd(item["price"] / (1 - item["discountPercentage"] / 100))
                    if item.get("discountPercentage", 0) >= 8
                    else None
                ),
                "stock": max(int(item.get("stock", 0)), 5),
                "category": our_category,
                "images": files,
            }
            # A sale must actually be a discount; the database enforces it.
            if entry["originalPrice"] and entry["originalPrice"] <= price:
                entry["originalPrice"] = None
            catalogue.append(entry)

    OUT.write_text(
        json.dumps(catalogue, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    photos = sum(len(entry["images"]) for entry in catalogue)
    on_sale = sum(1 for entry in catalogue if entry["originalPrice"])
    print(
        f"{len(catalogue)} sản phẩm, {photos} ảnh đã tải, "
        f"{on_sale} món đang giảm giá -> {OUT.name}"
    )


if __name__ == "__main__":
    main()
