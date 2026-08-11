"""Reset the database and fill it with a demo marketplace from Amazon-M2.

The catalogue is drawn from the same item space the recommender was trained
on, so a Semantic ID the model generates points at a product that really
exists here. Products come from the validation sessions plus their Semantic
ID neighbours — the neighbours are what a cluster-to-item expansion needs to
have something to expand into.

Six shops, live vouchers and reviews come with it.

Reviews are the part that takes the work. A review is purchase-gated on the
server, so the seed cannot insert one: each demo buyer registers, places an
order, pays it through the mock gateway's IPN, and only then may rate what
they bought. That is also why "đã bán" and the star averages are real — both
are computed from paid orders.

Run it whenever the demo data is gone — most often because the test suite
truncates every table it touches.

    docker compose up -d
    mock-openAPI:  uvicorn main:app --port 4001
    server:        uvicorn app.main:app --port 4000

    .venv/bin/python -m pip install -r requirements.txt
    .venv/bin/python scripts/seed_demo.py

Translation and image search each call out to the network once per product,
which dominates the runtime. Product preparation runs concurrently; tune it
when a network starts throttling, or skip the network work for a fast run:

    .venv/bin/python scripts/seed_demo.py --workers 6
    .venv/bin/python scripts/seed_demo.py --skip-images --skip-translation
"""

import argparse
import asyncio
import base64
import csv
import hashlib
import json
import logging
import math
import random
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock, local

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MOCK = "http://127.0.0.1:4001"
BACKEND = "http://127.0.0.1:4000"
REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTS_CSV = REPO_ROOT / "ai-recommendation/dataset/original/amazon-m2/products_train.csv"
SESSION_ROOT = REPO_ROOT / "ai-recommendation/dataset/preprocessed"
SEMANTIC_IDS = REPO_ROOT / "ai-recommendation/output/rq-vae/semantic_ids.parquet"
IMAGE_DIR = REPO_ROOT / "server/uploads/amazon-m2"
TRANSLATION_CACHE = Path(__file__).resolve().parent / ".amazon-m2-cache/translations.json"
IMAGE_MANIFEST = Path(__file__).resolve().parent / ".amazon-m2-cache/image-manifest.json"

# Same data every run, so a reseed doesn't quietly change the numbers the
# screenshots were taken against.
random.seed(20260723)

# Products are handed out by a hash of the brand, so no shop specialises and
# the names stay generic. (name, province, address, phone)
SHOPS = [
    ("V-Market Global 1", "Thành phố Hồ Chí Minh", "45 Cách Mạng Tháng 8, P.6, Quận 3", "0902 111 222"),
    ("V-Market Global 2", "Thành phố Hà Nội", "88 Trần Duy Hưng, P. Trung Hoà, Q. Cầu Giấy", "0903 333 444"),
    ("V-Market Global 3", "Tỉnh Bình Dương", "175 Đại lộ Bình Dương, P. Phú Hoà, TP. Thủ Dầu Một", "0907 222 333"),
    ("V-Market Global 4", "Thành phố Hà Nội", "56 Chùa Bộc, P. Quang Trung, Q. Đống Đa", "0908 444 555"),
    ("V-Market Global 5", "Thành phố Đà Nẵng", "12 Lê Duẩn, P. Thạch Thang, Q. Hải Châu", "0905 555 666"),
    ("V-Market Global 6", "Thành phố Cần Thơ", "31 Đại lộ Hoà Bình, P. Tân An, Q. Ninh Kiều", "0909 666 777"),
]

SHOP_DESCRIPTION = "Gian hàng Amazon-M2 dành cho bản demo hệ thống gợi ý."

# One list per shop. The second code on shop 1 is deliberately out of reach
# for a small basket, so checkout shows a live code beside a greyed-out one
# with "cần thêm …".
VOUCHERS = [
    [
        {"code": "VMG1GIAM25", "description": "Giảm 25% toàn shop, tối đa 2.000.000₫",
         "discountType": "PERCENT", "discountValue": 25, "maxDiscount": 2_000_000, "days": (-1, 14)},
        {"code": "VMG1GIAM5TRIEU", "description": "Giảm 5.000.000₫ cho đơn từ 60.000.000₫",
         "discountType": "AMOUNT", "discountValue": 5_000_000, "minOrder": 60_000_000, "days": (-1, 30)},
    ],
    [{"code": "VMG2GIAM20", "description": "Giảm 20% toàn shop, tối đa 200.000₫",
      "discountType": "PERCENT", "discountValue": 20, "maxDiscount": 200_000, "days": (-1, 10)}],
    [{"code": "VMG3GIAM15", "description": "Giảm 15% toàn shop, tối đa 300.000₫",
      "discountType": "PERCENT", "discountValue": 15, "maxDiscount": 300_000, "days": (-1, 20)}],
    [{"code": "VMG4GIAM100K", "description": "Giảm 100.000₫ cho đơn từ 800.000₫",
      "discountType": "AMOUNT", "discountValue": 100_000, "minOrder": 800_000, "days": (-1, 16)}],
    [{"code": "VMG5GIAM12", "description": "Giảm 12% toàn shop, tối đa 150.000₫",
      "discountType": "PERCENT", "discountValue": 12, "maxDiscount": 150_000, "days": (-1, 25)}],
    [{"code": "VMG6GIAM50K", "description": "Giảm 50.000₫ cho đơn từ 500.000₫",
      "discountType": "AMOUNT", "discountValue": 50_000, "minOrder": 500_000, "days": (-1, 18)}],
]

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


# --- small helpers ----------------------------------------------------------

def _svg_data_uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


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
        'font-weight="bold" fill="#ffffff" text-anchor="middle">'
        f"{name.strip()[0]}</text></svg>"
    )


def _stable_number(value: str) -> int:
    return int.from_bytes(hashlib.blake2b(value.encode(), digest_size=8).digest(), "big")


def _clean(value: object) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def call(base, path, payload=None, token=None, method=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        # A 422 names the field it rejected, but only in the body, which the
        # traceback throws away. Print it before re-raising.
        if error.code == 422:
            print(f"  {path} rejected: {error.read().decode('utf-8', 'ignore')[:400]}")
        raise


def token_for(name: str) -> str:
    user = call(MOCK, "/simulator/users", {"name": name})["data"]["user_id"]
    code = call(MOCK, "/simulator/authcode", {"user_id": user, "scopes": "profile phone"})["data"]["authCode"]
    return call(BACKEND, "/auth/session", {"authCode": code})["token"]


# --- picking which products to seed -----------------------------------------

def _take_session_products(path: Path, selected: dict, max_count: int, targets: set | None = None) -> None:
    """Add products from a session file, keeping each session's history whole."""
    import pyarrow.parquet as pq

    for batch in pq.ParquetFile(path).iter_batches(
        columns=["prev_items", "next_item"], batch_size=4096
    ):
        rows = batch.to_pydict()
        for previous, next_item in zip(rows["prev_items"], rows["next_item"]):
            next_id = _clean(next_item)
            if targets is not None and next_id:
                targets.add(next_id)
            for product_id in [next_id, *(previous or [])]:
                product_id = _clean(product_id)
                if product_id:
                    selected.setdefault(product_id, None)
                if len(selected) >= max_count:
                    return


def _take_sid_neighbours(
    semantic_ids_path: Path, targets: set, selected: dict, max_count: int, per_sid: int = 8
) -> None:
    """Add products sharing a Semantic ID with something already selected."""
    import pyarrow.parquet as pq

    columns = ["product_id", "sid_0", "sid_1", "sid_2"]
    parquet = pq.ParquetFile(semantic_ids_path)

    wanted = set()
    for batch in parquet.iter_batches(columns=columns, batch_size=65536):
        rows = batch.to_pydict()
        for product_id, a, b, c in zip(rows["product_id"], rows["sid_0"], rows["sid_1"], rows["sid_2"]):
            if product_id in targets:
                wanted.add((int(a), int(b), int(c)))
    if not wanted:
        return

    taken: dict = {}
    for batch in parquet.iter_batches(columns=columns, batch_size=65536):
        rows = batch.to_pydict()
        for product_id, a, b, c in zip(rows["product_id"], rows["sid_0"], rows["sid_1"], rows["sid_2"]):
            sid = (int(a), int(b), int(c))
            if sid not in wanted or taken.get(sid, 0) >= per_sid:
                continue
            selected.setdefault(str(product_id), None)
            taken[sid] = taken.get(sid, 0) + 1
            if len(selected) >= max_count:
                return


def select_product_ids(limit: int) -> list[str]:
    validation = SESSION_ROOT / "model_sessions_validation.parquet"
    train = SESSION_ROOT / "model_sessions_train.parquet"
    for path in (validation, train, SEMANTIC_IDS):
        if not path.is_file():
            raise FileNotFoundError(f"Amazon-M2 artifact not found: {path}")

    selected: dict = {}
    targets: set = set()
    _take_session_products(validation, selected, max(1, int(limit * 0.65)), targets)
    _take_sid_neighbours(SEMANTIC_IDS, targets, selected, limit)

    # Extra IDs stand in for rows rejected by moderation or missing a title.
    _take_session_products(train, selected, limit * 2)
    return list(selected)


def load_metadata(product_ids: list[str]) -> dict:
    """Read the one row per product with the most fields filled in."""
    if not PRODUCTS_CSV.is_file():
        raise FileNotFoundError(f"Amazon-M2 product metadata not found: {PRODUCTS_CSV}")

    wanted = set(product_ids)
    best: dict = {}
    csv.field_size_limit(10_000_000)
    with PRODUCTS_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            product_id = _clean(row.get("id"))
            if product_id not in wanted:
                continue
            score = sum(bool(_clean(row.get(f))) for f in
                        ("title", "desc", "brand", "color", "model", "material"))
            score += min(len(_clean(row.get("desc"))) // 200, 5)
            if product_id not in best or score > best[product_id][0]:
                best[product_id] = (score, row)
    return {product_id: row for product_id, (_, row) in best.items()}


def sale_original_price(price: int, product_id: str) -> int | None:
    """The struck-through price, for about a third of the catalogue.

    The seed needs enough discounted items that the home page's flash-sale
    strip fills its row instead of showing two lonely cards. Derived from
    the product id so a reseed marks down the same items.

    Returns None when the item is not on sale, or when rounding would land
    on the selling price — the server rejects a "sale" that saves nothing.
    """
    roll = _stable_number(product_id + ":sale") % 100
    if roll >= 35:
        return None
    percent = 10 + roll % 41
    original = int(round(price / (1 - percent / 100) / 1_000)) * 1_000
    return original if original > price else None


def to_vnd(row: dict, product_id: str) -> int:
    try:
        price = float(_clean(row.get("price")))
    except ValueError:
        price = math.nan
    if not math.isfinite(price) or price <= 0:
        return 50_000 + (_stable_number(product_id) % 1_950) * 1_000

    rate = {"UK": 33_000, "DE": 28_000, "FR": 28_000,
            "IT": 28_000, "ES": 28_000, "JP": 170}.get(_clean(row.get("locale")), 26_000)
    return min(max(int(round(price * rate / 1_000)) * 1_000, 10_000), 100_000_000)


# --- translation and images -------------------------------------------------

def _load_translations() -> dict:
    return json.loads(TRANSLATION_CACHE.read_text(encoding="utf-8")) if TRANSLATION_CACHE.is_file() else {}


def _save_translations(cache: dict, cache_lock: Lock | None = None) -> None:
    if cache_lock is not None:
        with cache_lock:
            snapshot = dict(cache)
    else:
        snapshot = cache
    TRANSLATION_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TRANSLATION_CACHE.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _load_image_manifest() -> dict:
    if not IMAGE_MANIFEST.is_file():
        return {}
    try:
        data = json.loads(IMAGE_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_image_manifest(manifest: dict, manifest_lock: Lock) -> None:
    """Atomically persist a progress checkpoint for resumable image work."""
    with manifest_lock:
        snapshot = dict(manifest)
        IMAGE_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        temporary = IMAGE_MANIFEST.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(IMAGE_MANIFEST)


# Google serves its error page with a 200, and deep-translator hands the body
# back as if it were a translation. Without this check a single 500 gets
# cached as a product name and stays there for every later run.
ERROR_PAGE_MARKERS = ("That’s an error", "That's an error", "Server Error", "Error 500")


def translate(text: str, translator, cache: dict, cache_lock: Lock) -> str:
    text = text.strip()
    if not text or translator is None:
        return text
    key = hashlib.sha256(text.encode("utf-8")).hexdigest()
    with cache_lock:
        if key in cache:
            return cache[key]

    try:
        result = translator.translate(text) or text
    except Exception as error:  # noqa: BLE001
        print(f"  translation failed: {error}")
        return text
    if any(marker in result for marker in ERROR_PAGE_MARKERS):
        print("  translation failed: Google returned an error page")
        return text

    # Another worker may have translated the same description while this
    # request was in flight. Keep whichever completed first; both are valid.
    with cache_lock:
        return cache.setdefault(key, result)


def quiet_crawler_logs() -> None:
    """icrawler calls logging.basicConfig at INFO on the root logger, which
    buries this script's own progress lines. The downloader is quieted
    hardest: a 403 or a dead host for one candidate is routine — two more
    candidates follow it, and a product with no image at all is allowed."""
    for name in ("icrawler.crawler", "feeder", "parser"):
        logging.getLogger(name).setLevel(logging.ERROR)
    logging.getLogger("downloader").setLevel(logging.CRITICAL)


AMAZON_DOMAINS = {
    "DE": "amazon.de",
    "ES": "amazon.es",
    "FR": "amazon.fr",
    "IT": "amazon.it",
    "JP": "amazon.co.jp",
    "UK": "amazon.co.uk",
}


def _image_queries(
    product_id: str, title: str, brand: str, model: str, locale: str
) -> list[str]:
    amazon_domain = AMAZON_DOMAINS.get(locale.upper(), "amazon.com")
    product_terms = " ".join(
        part for part in (product_id, brand, model, title[:100]) if part
    )
    candidates = [
        f"site:{amazon_domain} {product_terms}",
        f"site:amazon.com {product_terms}",
        product_terms,
        " ".join(part for part in (product_id, brand, title[:100]) if part),
        " ".join(part for part in (model, brand, title[:120]) if part),
    ]
    return list(dict.fromkeys(query.strip() for query in candidates if query.strip()))


def _query_signature(queries: list[str]) -> str:
    payload = json.dumps(queries, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def crawl_image(
    product_id: str,
    title: str,
    brand: str,
    model: str,
    locale: str,
    manifest: dict,
    manifest_lock: Lock,
) -> str | None:
    """Take the first valid Bing photo and remember it for the next run."""
    from icrawler.builtin import BingImageCrawler
    from PIL import Image

    safe_id = "".join(c for c in product_id if c.isalnum() or c in "-_")
    queries = _image_queries(product_id, title, brand, model, locale)
    signature = _query_signature(queries)
    with manifest_lock:
        cached = manifest.get(product_id)
    if cached and cached.get("querySignature") == signature:
        if cached.get("status") == "missing":
            return None
        selected = cached.get("selected") or {}
        cached_file = IMAGE_DIR / str(selected.get("file") or "")
        if cached_file.is_file():
            return f"{BACKEND}/uploads/amazon-m2/{cached_file.name}"

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    selected = None
    try:
        with tempfile.TemporaryDirectory(prefix=f"amazon-m2-{safe_id}-") as temp:
            temp_path = Path(temp)
            for query_index, query in enumerate(queries):
                query_dir = temp_path / str(query_index)
                BingImageCrawler(
                    storage={"root_dir": str(query_dir)},
                    downloader_threads=3,
                    log_level=logging.ERROR,
                ).crawl(
                    keyword=query,
                    filters={"type": "photo", "size": "medium"},
                    max_num=4,
                    min_size=(300, 300),
                )

                for downloaded in sorted(query_dir.glob("*")):
                    try:
                        with Image.open(downloaded) as image:
                            image.verify()
                            width, height = image.size
                            image_format = (image.format or "JPEG").lower()
                    except Exception:  # noqa: BLE001
                        continue
                    suffix = {"jpeg": ".jpg", "png": ".png", "webp": ".webp"}.get(
                        image_format
                    )
                    if suffix is None:
                        continue
                    destination = IMAGE_DIR / f"{safe_id}{suffix}"
                    shutil.copyfile(downloaded, destination)
                    selected = {
                        "file": destination.name,
                        "query": query,
                        "width": width,
                        "height": height,
                    }
                    break
                if selected:
                    break
    except Exception as error:  # noqa: BLE001
        print(f"  image failed for {product_id}: {error}")

    entry = {
        "status": "accepted" if selected else "missing",
        "querySignature": signature,
        "queries": queries,
        "selected": selected,
    }
    with manifest_lock:
        manifest[product_id] = entry
    if selected:
        return f"{BACKEND}/uploads/amazon-m2/{selected['file']}"
    return None


def build_catalogue(
    limit: int, do_translate: bool, do_images: bool, workers: int
) -> list[dict]:
    from app.products.moderation import banned_terms_in

    if do_images:
        quiet_crawler_logs()

    product_ids = select_product_ids(limit)
    metadata = load_metadata(product_ids)

    GoogleTranslator = None
    if do_translate:
        from deep_translator import GoogleTranslator as Translator

        GoogleTranslator = Translator
    cache = _load_translations()
    cache_lock = Lock()
    image_manifest = _load_image_manifest()
    image_manifest_lock = Lock()
    worker_state = local()

    def translator_for_worker():
        if GoogleTranslator is None:
            return None
        translator = getattr(worker_state, "translator", None)
        if translator is None:
            # deep-translator keeps request state on the instance, so each
            # worker owns one instead of sharing it across threads.
            translator = GoogleTranslator(source="auto", target="vi")
            worker_state.translator = translator
        return translator

    def prepare(product_id: str) -> dict | None:
        row = metadata.get(product_id)
        if row is None:
            return None
        raw_title = _clean(row.get("title"))
        if not raw_title:
            return None

        brand = _clean(row.get("brand"))
        model = _clean(row.get("model"))
        locale = _clean(row.get("locale"))
        translator = translator_for_worker()
        name = translate(raw_title, translator, cache, cache_lock)[:200]
        description = translate(
            _clean(row.get("desc"))[:3000] or raw_title,
            translator,
            cache,
            cache_lock,
        )

        details = [
            ("Thương hiệu", brand),
            ("Màu sắc", _clean(row.get("color"))),
            ("Kích thước", _clean(row.get("size"))),
            ("Mẫu", model),
            ("Chất liệu", _clean(row.get("material"))),
            ("Tác giả", _clean(row.get("author"))),
        ]
        spec = ". ".join(f"{label}: {value}" for label, value in details if value)
        if spec:
            description = f"{description}\n\n{spec}."
        description = description[:4000]
        if banned_terms_in(name, description):
            return None

        image = None
        if do_images:
            image = crawl_image(
                product_id,
                raw_title,
                brand,
                model,
                locale,
                image_manifest,
                image_manifest_lock,
            )
            # A small per-worker pause is enough courtesy once several
            # products are in flight; it no longer serialises the catalogue.
            time.sleep(0.2)

        price = to_vnd(row, product_id)
        return {
            "sku": product_id,
            "name": name,
            "description": description,
            "unit": brand[:60] or None,
            "price": price,
            "originalPrice": sale_original_price(price, product_id),
            "stock": 20 + _stable_number(product_id) % 81,
            "image": image,
            "shopIndex": _stable_number(brand or product_id) % len(SHOPS),
        }

    catalogue: list[dict] = []
    with_image = 0
    # Bounded batches matter here: product_ids contains fallbacks for rows
    # rejected by moderation. Submitting the whole list would keep fetching
    # thousands of unnecessary images after the requested limit was reached.
    batch_size = max(workers * 3, 1)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for start in range(0, len(product_ids), batch_size):
            batch = product_ids[start : start + batch_size]
            for entry in executor.map(prepare, batch):
                if entry is None:
                    continue
                catalogue.append(entry)
                with_image += 1 if entry["image"] else 0

                if len(catalogue) % 10 == 0:
                    _save_translations(cache, cache_lock)
                    if do_images:
                        _save_image_manifest(image_manifest, image_manifest_lock)
                    suffix = f", {with_image} with an image" if do_images else ""
                    print(f"  prepared {len(catalogue)}/{limit} products{suffix}")
                if len(catalogue) >= limit:
                    break
            if len(catalogue) >= limit:
                break

    _save_translations(cache, cache_lock)
    if do_images:
        _save_image_manifest(image_manifest, image_manifest_lock)
    if len(catalogue) < limit:
        print(f"Warning: prepared {len(catalogue)} of the {limit} products requested")
    return catalogue


# --- writing it to the database ---------------------------------------------

async def truncate() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.config import settings

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE products, shops, users CASCADE"))
    await engine.dispose()


async def write_semantic_ids(skus: list[str]) -> int:
    """Copy each product's Semantic ID from the RQ-VAE output into its row.

    Straight SQL rather than the API: a SID is model output, not something a
    seller types, so no endpoint accepts one. The recommender reads these
    columns to find products near what a shopper has been looking at.
    """
    import pyarrow.parquet as pq
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.config import settings

    wanted = set(skus)
    updates = []
    columns = ["product_id", "sid_0", "sid_1", "sid_2"]
    for batch in pq.ParquetFile(SEMANTIC_IDS).iter_batches(columns=columns, batch_size=65536):
        rows = batch.to_pydict()
        for product_id, a, b, c in zip(*(rows[name] for name in columns)):
            if product_id in wanted:
                updates.append({"sku": product_id, "a": int(a), "b": int(b), "c": int(c)})

    if not updates:
        return 0
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE products SET sid_0 = :a, sid_1 = :b, sid_2 = :c WHERE sku = :sku"),
            updates,
        )
    await engine.dispose()
    return len(updates)


def seed_shops(catalogue: list[dict], workers: int) -> list[dict]:
    buckets = [[] for _ in SHOPS]
    for entry in catalogue:
        buckets[entry["shopIndex"] % len(SHOPS)].append(entry)

    listed: list[dict] = []
    for index, (name, province, address, phone) in enumerate(SHOPS):
        token = token_for(f"Chủ shop {index + 1}")
        call(BACKEND, "/shops", {
            "name": name,
            "description": SHOP_DESCRIPTION,
            "province": province,
            "address": address,
            "phone": phone,
            "imageUrl": _banner_uri(index),
            "logoUrl": _logo_uri(name, index),
        }, token)

        def create_product(entry: dict) -> dict:
            created = call(BACKEND, "/products", {
                "sku": entry["sku"],
                "name": entry["name"],
                "description": entry["description"],
                "unit": entry["unit"],
                "price": entry["price"],
                "originalPrice": entry["originalPrice"],
                "stock": entry["stock"],
                "imageUrl": entry["image"],
                "imageUrls": [entry["image"]] if entry["image"] else None,
            }, token)
            return {"id": created["id"], "name": created["name"]}

        # Product creation is independent inside a shop. A small pool keeps
        # the local API and Postgres busy without overrunning their pools.
        with ThreadPoolExecutor(max_workers=workers) as executor:
            listed.extend(executor.map(create_product, buckets[index]))

        codes = []
        for template in VOUCHERS[index]:
            voucher = dict(template)
            start_days, end_days = voucher.pop("days")
            now = datetime.now(timezone.utc)
            voucher["startsAt"] = (now + timedelta(days=start_days)).isoformat()
            voucher["endsAt"] = (now + timedelta(days=end_days)).isoformat()
            call(BACKEND, "/vouchers", voucher, token)
            codes.append(voucher["code"])

        print(f"  {name}: {len(buckets[index])} products, vouchers {', '.join(codes)}")

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
        basket = random.sample(listed, random.randint(min(6, maximum), maximum))

        # Checkout is all-or-nothing, so one sold-out line kills the basket.
        # That is correct behaviour, not a seed bug — skip the buyer.
        try:
            order = call(BACKEND, "/orders", {
                "address": (f"{random.randint(1, 250)} Nguyễn Trãi, P. Bến Thành, "
                            "Quận 1, Thành phố Hồ Chí Minh"),
                "items": [{"productId": item["id"], "qty": 1} for item in basket],
            }, token)
        except urllib.error.HTTPError as error:
            if error.code != 409:
                raise
            print(f"  skipped {name}: the basket held a sold-out item")
            continue

        payment = call(MOCK, "/simulator/payment/init",
                       {"orderId": order["id"], "amount": int(order["total"])})["data"]
        call(MOCK, f"/simulator/payment/{payment['paymentId']}/confirm", {})
        # Count what actually settled rather than assuming: a lost webhook
        # would otherwise be reported as a paid order with no reviews.
        if call(BACKEND, f"/orders/{order['id']}", token=token)["status"] == "PAID":
            paid += 1

        for item in random.sample(basket, k=max(int(len(basket) * 0.75), 1)):
            rating = random.choice(_RATING_POOL)
            try:
                call(BACKEND, f"/products/{item['id']}/reviews",
                     {"rating": rating, "comment": random.choice(COMMENTS[rating])}, token)
                written += 1
            except urllib.error.HTTPError as error:
                # One review per buyer per product; a repeat is harmless.
                if error.code not in (403, 409):
                    raise
    return written, paid


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed the V-Market demo database")
    parser.add_argument("--limit", type=int, default=5000,
                        help="Number of Amazon-M2 products to seed")
    parser.add_argument("--workers", type=int, default=6,
                        help="Concurrent preparation/API workers")
    parser.add_argument("--skip-translation", action="store_true",
                        help="Keep the original Amazon-M2 title and description")
    parser.add_argument("--skip-images", action="store_true",
                        help="Do not search Bing Images")
    parser.add_argument("--skip-reviews", action="store_true",
                        help="Seed shops and products without orders and reviews")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be at least 1")
    if not 1 <= args.workers <= 16:
        parser.error("--workers must be between 1 and 16")
    return args


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()

    catalogue = build_catalogue(
        limit=args.limit,
        do_translate=not args.skip_translation,
        do_images=not args.skip_images,
        workers=args.workers,
    )

    asyncio.run(truncate())
    listed = seed_shops(catalogue, workers=args.workers)

    tagged = asyncio.run(write_semantic_ids([entry["sku"] for entry in catalogue]))
    print(f"  tagged {tagged} products with a Semantic ID")

    if args.skip_reviews:
        print(f"\nDone: {len(SHOPS)} shops, {len(listed)} products.")
    else:
        print(f"\nCreating orders and reviews for {len(BUYER_NAMES)} buyers...")
        reviews, paid = seed_reviews(listed)
        print(f"\nDone: {len(SHOPS)} shops, {len(listed)} products, "
              f"{paid}/{len(BUYER_NAMES)} orders paid, {reviews} reviews.")
