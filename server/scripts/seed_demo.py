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

To seed a recommendation demo from Amazon-M2 instead:

    .venv\\Scripts\\python.exe -m pip install -r requirements.txt
    .venv\\Scripts\\python.exe scripts/seed_demo.py --amazon-m2 --limit 500
"""

import argparse
import asyncio
import base64
import csv
import hashlib
import json
import math
import random
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MOCK = "http://127.0.0.1:4001"
BACKEND = "http://127.0.0.1:4000"
CATALOGUE = Path(__file__).resolve().parent / "demo_catalogue.json"
REPO_ROOT = Path(__file__).resolve().parents[2]
AMAZON_M2_ROOT = REPO_ROOT / "ai-recommendation/dataset"
AMAZON_PRODUCTS = AMAZON_M2_ROOT / "original/amazon-m2/products_train.csv"
AMAZON_SESSION_ROOT = AMAZON_M2_ROOT / "preprocessed"
AMAZON_SEMANTIC_IDS = REPO_ROOT / "ai-recommendation/output/rq-vae/semantic_ids.parquet"
AMAZON_IMAGE_DIR = REPO_ROOT / "server/uploads/amazon-m2"
AMAZON_CACHE_DIR = Path(__file__).resolve().parent / ".amazon-m2-cache"
TRANSLATION_CACHE = AMAZON_CACHE_DIR / "translations.json"

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

AMAZON_SHOPS = [
    (
        f"V-Market Global {index + 1}",
        "Gian hàng Amazon-M2 dành cho bản demo hệ thống gợi ý.",
        province,
        address,
        phone,
        [],
    )
    for index, (_, _, province, address, phone, _) in enumerate(SHOPS)
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


def _stable_number(value: str) -> int:
    digest = hashlib.blake2b(value.encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def _add_session_products(
    path: Path,
    selected: dict[str, None],
    max_count: int,
    targets: set[str] | None = None,
) -> None:
    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(path)
    for batch in parquet.iter_batches(
        columns=["prev_items", "next_item"], batch_size=4096
    ):
        rows = batch.to_pydict()
        for previous, next_item in zip(rows["prev_items"], rows["next_item"]):
            next_id = str(next_item).strip()
            if targets is not None and next_id:
                targets.add(next_id)

            # Keep the labelled next item and its complete session history.
            for product_id in [next_id, *(previous or [])]:
                product_id = str(product_id).strip()
                if product_id:
                    selected.setdefault(product_id, None)
                if len(selected) >= max_count:
                    return


def _read_predicted_sids(path: Path | None) -> set[tuple[int, int, int]]:
    if path is None:
        return set()
    if not path.is_file():
        raise FileNotFoundError(f"Predicted SID file not found: {path}")

    import pyarrow.parquet as pq

    table = pq.read_table(path, columns=["sid_0", "sid_1", "sid_2"])
    columns = table.to_pydict()
    return {
        (int(a), int(b), int(c))
        for a, b, c in zip(columns["sid_0"], columns["sid_1"], columns["sid_2"])
    }


def _expand_semantic_ids(
    semantic_ids_path: Path,
    target_ids: set[str],
    predicted_sids: set[tuple[int, int, int]],
    selected: dict[str, None],
    max_count: int,
    items_per_sid: int = 8,
) -> None:
    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(semantic_ids_path)
    target_sids: set[tuple[int, int, int]] = set()
    for batch in parquet.iter_batches(
        columns=["product_id", "sid_0", "sid_1", "sid_2"], batch_size=65536
    ):
        rows = batch.to_pydict()
        for product_id, a, b, c in zip(
            rows["product_id"], rows["sid_0"], rows["sid_1"], rows["sid_2"]
        ):
            if product_id in target_ids:
                target_sids.add((int(a), int(b), int(c)))

    wanted_sids = predicted_sids | target_sids
    if not wanted_sids:
        return

    per_sid: dict[tuple[int, int, int], int] = {}
    for batch in parquet.iter_batches(
        columns=["product_id", "sid_0", "sid_1", "sid_2"], batch_size=65536
    ):
        rows = batch.to_pydict()
        for product_id, a, b, c in zip(
            rows["product_id"], rows["sid_0"], rows["sid_1"], rows["sid_2"]
        ):
            sid = (int(a), int(b), int(c))
            if sid not in wanted_sids or per_sid.get(sid, 0) >= items_per_sid:
                continue
            selected.setdefault(str(product_id), None)
            per_sid[sid] = per_sid.get(sid, 0) + 1
            if len(selected) >= max_count:
                return


def select_amazon_product_ids(
    limit: int,
    session_root: Path,
    semantic_ids_path: Path,
    predicted_sids_path: Path | None,
) -> list[str]:
    validation_path = session_root / "model_sessions_validation.parquet"
    train_path = session_root / "model_sessions_train.parquet"
    for path in (validation_path, train_path, semantic_ids_path):
        if not path.is_file():
            raise FileNotFoundError(f"Amazon-M2 artifact not found: {path}")

    selected: dict[str, None] = {}
    validation_targets: set[str] = set()
    session_budget = max(1, int(limit * 0.65))
    _add_session_products(
        validation_path, selected, session_budget, validation_targets
    )

    predicted_sids = _read_predicted_sids(predicted_sids_path)
    _expand_semantic_ids(
        semantic_ids_path,
        validation_targets,
        predicted_sids,
        selected,
        limit,
    )
    _add_session_products(train_path, selected, limit)

    # Extra IDs replace metadata rows rejected by moderation or missing text.
    _add_session_products(train_path, selected, max(limit * 2, limit + 100))
    return list(selected)


def _clean_field(value: object) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def load_amazon_metadata(path: Path, product_ids: list[str]) -> dict[str, dict]:
    if not path.is_file():
        raise FileNotFoundError(f"Amazon-M2 product metadata not found: {path}")

    wanted = set(product_ids)
    best: dict[str, tuple[int, dict]] = {}
    csv.field_size_limit(10_000_000)
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            product_id = _clean_field(row.get("id"))
            if product_id not in wanted:
                continue
            score = sum(
                bool(_clean_field(row.get(field)))
                for field in ("title", "desc", "brand", "color", "model", "material")
            )
            score += min(len(_clean_field(row.get("desc"))) // 200, 5)
            if product_id not in best or score > best[product_id][0]:
                best[product_id] = (score, row)
    return {product_id: row for product_id, (_, row) in best.items()}


def _to_vnd(row: dict, product_id: str) -> int:
    raw_price = _clean_field(row.get("price"))
    try:
        price = float(raw_price)
    except ValueError:
        price = math.nan

    if not math.isfinite(price) or price <= 0:
        return 50_000 + (_stable_number(product_id) % 1_950) * 1_000

    rate = {
        "UK": 33_000,
        "DE": 28_000,
        "FR": 28_000,
        "IT": 28_000,
        "ES": 28_000,
        "JP": 170,
    }.get(_clean_field(row.get("locale")), 26_000)
    converted = int(round(price * rate / 1_000)) * 1_000
    return min(max(converted, 10_000), 100_000_000)


def _load_translation_cache() -> dict[str, str]:
    if not TRANSLATION_CACHE.is_file():
        return {}
    return json.loads(TRANSLATION_CACHE.read_text(encoding="utf-8"))


def _save_translation_cache(cache: dict[str, str]) -> None:
    AMAZON_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    TRANSLATION_CACHE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _translate(text: str, translator, cache: dict[str, str]) -> str:
    text = text.strip()
    if not text or translator is None:
        return text
    key = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if key in cache:
        return cache[key]
    try:
        translated = translator.translate(text)
    except Exception as error:  # noqa: BLE001
        print(f"  translation failed: {error}")
        return text
    cache[key] = translated or text
    return cache[key]


def _crawl_product_image(
    product_id: str,
    title: str,
    brand: str,
    model: str,
    image_license: str,
) -> str | None:
    safe_id = "".join(char for char in product_id if char.isalnum() or char in "-_")
    AMAZON_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(AMAZON_IMAGE_DIR.glob(f"{safe_id}.*"))
    if existing:
        return f"{BACKEND}/uploads/amazon-m2/{existing[0].name}"

    from icrawler.builtin import GoogleImageCrawler
    from PIL import Image

    query = " ".join(
        part for part in (f'"{product_id}"', brand, model, title[:140]) if part
    )
    try:
        with tempfile.TemporaryDirectory(prefix=f"amazon-m2-{safe_id}-") as temp:
            crawler = GoogleImageCrawler(storage={"root_dir": temp})
            crawler.crawl(
                keyword=query,
                filters={
                    "type": "photo",
                    "size": "medium",
                    "license": image_license,
                },
                max_num=3,
                min_size=(300, 300),
            )
            for downloaded in sorted(Path(temp).iterdir()):
                try:
                    with Image.open(downloaded) as image:
                        image.verify()
                        image_format = (image.format or "JPEG").lower()
                except Exception:  # noqa: BLE001
                    continue
                suffix = {"jpeg": ".jpg", "png": ".png", "webp": ".webp"}.get(
                    image_format
                )
                if suffix is None:
                    continue
                destination = AMAZON_IMAGE_DIR / f"{safe_id}{suffix}"
                shutil.copyfile(downloaded, destination)
                return f"{BACKEND}/uploads/amazon-m2/{destination.name}"
    except Exception as error:  # noqa: BLE001
        print(f"  image failed for {product_id}: {error}")
    return None


def prepare_amazon_catalogue(
    limit: int,
    session_root: Path,
    semantic_ids_path: Path,
    predicted_sids_path: Path | None,
    translate: bool,
    crawl_images: bool,
    image_license: str,
) -> list[dict]:
    from app.products.moderation import banned_terms_in

    product_ids = select_amazon_product_ids(
        limit, session_root, semantic_ids_path, predicted_sids_path
    )
    metadata = load_amazon_metadata(AMAZON_PRODUCTS, product_ids)

    translator = None
    if translate:
        from deep_translator import GoogleTranslator

        translator = GoogleTranslator(source="auto", target="vi")
    translation_cache = _load_translation_cache()

    catalogue: list[dict] = []
    for index, product_id in enumerate(product_ids):
        row = metadata.get(product_id)
        if row is None:
            continue
        raw_title = _clean_field(row.get("title"))
        if not raw_title:
            continue
        raw_description = _clean_field(row.get("desc"))[:3000] or raw_title
        brand = _clean_field(row.get("brand"))
        model = _clean_field(row.get("model"))

        title = _translate(raw_title, translator, translation_cache)[:200]
        description = _translate(raw_description, translator, translation_cache)
        details = [
            ("Thương hiệu", brand),
            ("Màu sắc", _clean_field(row.get("color"))),
            ("Kích thước", _clean_field(row.get("size"))),
            ("Mẫu", model),
            ("Chất liệu", _clean_field(row.get("material"))),
            ("Tác giả", _clean_field(row.get("author"))),
        ]
        specification = ". ".join(
            f"{label}: {value}" for label, value in details if value
        )
        if specification:
            description = f"{description}\n\n{specification}."
        description = description[:4000]
        if banned_terms_in(title, description):
            continue

        image = None
        if crawl_images:
            image = _crawl_product_image(
                product_id, raw_title, brand, model, image_license
            )
            time.sleep(0.2)

        catalogue.append(
            {
                "sku": product_id,
                "name": title,
                "description": description,
                "unit": brand or None,
                "price": _to_vnd(row, product_id),
                "originalPrice": None,
                "stock": 20 + _stable_number(product_id) % 81,
                "category": None,
                "images": [image] if image else [],
                "shopIndex": _stable_number(brand or product_id) % len(AMAZON_SHOPS),
            }
        )
        if index % 10 == 0:
            _save_translation_cache(translation_cache)
            print(f"  prepared {len(catalogue)}/{limit} Amazon-M2 products")
        if len(catalogue) >= limit:
            break

    _save_translation_cache(translation_cache)
    if len(catalogue) < limit:
        print(f"Warning: prepared {len(catalogue)} of {limit} requested products")
    return catalogue


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
    category = entry.get("category")
    if category == "thoi-trang":
        values, group = SIZES_CLOTHES, "Size"
    elif category == "giay-dep":
        values, group = SIZES_SHOES, "Size"
    elif category == "phu-kien" and "Túi xách" in entry.get("name", ""):
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


def seed_shops(catalogue: list[dict], shops=SHOPS) -> list[dict]:
    if any("shopIndex" in entry for entry in catalogue):
        buckets = [[] for _ in shops]
        for entry in catalogue:
            buckets[int(entry.get("shopIndex", 0)) % len(shops)].append(entry)
    else:
        # Hand each shop the categories it sells; the last shop sweeps up
        # whatever is left so nothing in the catalogue goes unlisted.
        claimed = {c for _, _, _, _, _, cats in shops for c in cats}
        buckets = []
        for *_, cats in shops:
            if cats:
                buckets.append([e for e in catalogue if e["category"] in cats])
            else:
                buckets.append(
                    [e for e in catalogue if e["category"] not in claimed]
                )

    listed: list[dict] = []
    for index, (name, desc, province, address, phone, _) in enumerate(shops):
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
            images = entry.get("images") or []
            payload = {
                "sku": entry.get("sku"),
                "name": entry["name"][:200],
                "description": entry["description"],
                "unit": entry.get("unit"),
                "price": entry["price"],
                "stock": entry["stock"],
                "category": entry.get("category"),
                "imageUrl": images[0] if images else None,
                "imageUrls": images or None,
            }
            if entry.get("originalPrice"):
                payload["originalPrice"] = entry["originalPrice"]

            options = variants_for(entry, entry["stock"])
            if options:
                payload["variants"] = options

            created = call(BACKEND, "/products", payload, token)
            listed.append(
                {
                    "id": created["id"],
                    "sku": created.get("sku"),
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


def seed_reviews(listed: list[dict]) -> tuple[int, int]:
    """Buy, pay, then rate — the only order the server permits."""
    if not listed:
        return 0, 0
    written = 0
    paid = 0
    for name in BUYER_NAMES:
        token = token_for(name)
        maximum = min(11, len(listed))
        minimum = min(6, maximum)
        basket = random.sample(listed, random.randint(minimum, maximum))

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
        # Count what actually settled rather than assuming: a lost webhook
        # would otherwise be reported as a paid order with no reviews.
        if call(BACKEND, f"/orders/{order['id']}", token=token)["status"] == "PAID":
            paid += 1

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
    return written, paid


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed the V-Market demo database")
    parser.add_argument(
        "--amazon-m2",
        action="store_true",
        help="Seed products selected from Amazon-M2 instead of demo_catalogue.json",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Number of Amazon-M2 products to seed (default: 500)",
    )
    parser.add_argument(
        "--session-root",
        type=Path,
        default=AMAZON_SESSION_ROOT,
        help="Folder containing preprocessed train and validation sessions",
    )
    parser.add_argument(
        "--semantic-ids",
        type=Path,
        default=AMAZON_SEMANTIC_IDS,
        help="semantic_ids.parquet produced by RQ-VAE training",
    )
    parser.add_argument(
        "--predicted-sids",
        type=Path,
        help="Optional Parquet with sid_0, sid_1 and sid_2 predictions",
    )
    parser.add_argument(
        "--skip-translation",
        action="store_true",
        help="Keep the original Amazon-M2 title and description",
    )
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="Do not search Google Images",
    )
    parser.add_argument(
        "--image-license",
        choices=("noncommercial", "commercial"),
        default="noncommercial",
        help="Google Images usage-rights filter (default: noncommercial)",
    )
    parser.add_argument(
        "--skip-reviews",
        action="store_true",
        help="Seed shops and products without synthetic paid orders and reviews",
    )
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be at least 1")
    return args


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()

    if args.amazon_m2:
        catalogue = prepare_amazon_catalogue(
            limit=args.limit,
            session_root=args.session_root.resolve(),
            semantic_ids_path=args.semantic_ids.resolve(),
            predicted_sids_path=(
                args.predicted_sids.resolve() if args.predicted_sids else None
            ),
            translate=not args.skip_translation,
            crawl_images=not args.skip_images,
            image_license=args.image_license,
        )
        shops = AMAZON_SHOPS
    else:
        if not CATALOGUE.exists():
            sys.exit(
                "Thiếu demo_catalogue.json — chạy scripts/build_catalogue.py trước."
            )
        catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
        shops = SHOPS

    asyncio.run(truncate())
    listed = seed_shops(catalogue, shops)
    if args.skip_reviews:
        print(f"\nXong: {len(shops)} shop, {len(listed)} sản phẩm.")
    else:
        print(f"\nĐang tạo đơn và đánh giá cho {len(BUYER_NAMES)} người mua…")
        reviews, paid = seed_reviews(listed)
        print(
            f"\nXong: {len(shops)} shop, {len(listed)} sản phẩm, "
            f"{paid}/{len(BUYER_NAMES)} đơn đã thanh toán, {reviews} đánh giá."
        )
