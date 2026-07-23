"""Products.

Authorisation here is two hops, unlike shops: a product belongs to a shop,
and a shop belongs to a seller. Owning the product means owning the shop it
sits in — checked server-side, never trusted from the request.
"""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentSeller
from app.db import get_session
from app.products import store as products
from app.products.store import Product
from app.reviews import store as reviews
from app.shops import store as shops
from app.users.store import MarketUser

router = APIRouter(tags=["Products"])

Session = Annotated[AsyncSession, Depends(get_session)]


class CreateProductRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    unit: str | None = Field(default=None, max_length=60)
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    # Set = the product is on sale at `price`; this is the struck-through
    # price. Mirrors the database CHECK, so the caller gets a 422 with a
    # message instead of a bare IntegrityError.
    originalPrice: Decimal | None = Field(
        default=None, gt=0, max_digits=12, decimal_places=2
    )
    stock: int = Field(ge=0)
    imageUrl: str | None = None
    imageUrls: list[str] | None = Field(default=None, max_length=8)

    @model_validator(mode="after")
    def sale_must_be_a_discount(self):
        if self.originalPrice is not None and self.originalPrice <= self.price:
            raise ValueError("originalPrice must be greater than price")
        return self


class UpdateProductRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=4000)
    price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    stock: int | None = Field(default=None, ge=0)
    imageUrl: str | None = None
    imageUrls: list[str] | None = Field(default=None, max_length=8)
    status: str | None = Field(default=None, pattern="^(ACTIVE|HIDDEN)$")


def _serialise(product: Product) -> dict:
    return {
        "id": product.id,
        "shopId": product.shop_id,
        "name": product.name,
        "description": product.description,
        "unit": product.unit,
        # A number, not a string: VND is whole đồng and stays far below the
        # 2^53 limit where JSON numbers stop being exact. What must not
        # happen is arithmetic on the client — order totals come from here.
        "price": float(product.price),
        "originalPrice": (
            float(product.original_price)
            if product.original_price is not None
            else None
        ),
        "stock": product.stock,
        "imageUrl": product.image_url,
        "imageUrls": product.image_urls
        or ([product.image_url] if product.image_url else []),
        "status": product.status,
    }


def _list_item(row: dict) -> dict:
    """A storefront row: the product plus the card's extra data — shop name
    and province, average rating, and units sold."""
    return {
        **_serialise(row["product"]),
        "shopName": row["shopName"],
        "shopProvince": row["shopProvince"],
        "ratingAverage": row["ratingAverage"],
        "ratingCount": row["ratingCount"],
        "sold": row["sold"],
    }


async def _my_shop(session: AsyncSession, seller: MarketUser):
    shop = await shops.find_by_owner(session, seller.id)
    if shop is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No shop yet"
        )
    return shop


@router.get("/shops/{shop_id}/products")
async def list_shop_products(
    shop_id: str,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """Public: the storefront, which must work without login.

    Hidden products are never included — that is the whole point of the
    flag, and this endpoint has no way to ask for them.
    """
    page = await products.list_for_shop(
        session, shop_id, limit=limit, offset=offset
    )
    return {
        "items": [_list_item(row) for row in page],
        "hasMore": len(page) == limit,
    }


@router.get("/products")
async def list_products(
    session: Session,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    onSale: Annotated[bool, Query()] = False,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> dict:
    """Public: the marketplace storefront across all shops.

    Must work without login, like every browsing endpoint. Each item
    carries its shop's name so the card can show where it comes from.
    ?onSale=true keeps only discounted items — the flash-sale strip.
    ?q=… searches by product or shop name across the whole catalogue.
    """
    page = await products.list_active(
        session, limit=limit, offset=offset, on_sale=onSale, q=q
    )
    return {
        "items": [_list_item(row) for row in page],
        "hasMore": len(page) == limit,
    }


@router.get("/products/mine")
async def list_my_products(
    seller: CurrentSeller,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """The seller's own shop, hidden products included."""
    shop = await _my_shop(session, seller)
    page = await products.list_for_shop(
        session, shop.id, limit=limit, offset=offset, include_hidden=True
    )
    return {
        "items": [_list_item(row) for row in page],
        "hasMore": len(page) == limit,
    }


@router.post("/products", status_code=status.HTTP_201_CREATED)
async def create_product(
    body: CreateProductRequest, seller: CurrentSeller, session: Session
) -> dict:
    # The shop comes from who is calling, never from the request body —
    # otherwise a seller could post products into someone else's shop.
    shop = await _my_shop(session, seller)

    product = await products.create_product(
        session,
        shop_id=shop.id,
        name=body.name,
        description=body.description,
        unit=body.unit,
        price=body.price,
        original_price=body.originalPrice,
        stock=body.stock,
        image_url=body.imageUrl,
        image_urls=body.imageUrls,
    )
    return _serialise(product)


@router.patch("/products/{product_id}")
async def update_product(
    product_id: str,
    body: UpdateProductRequest,
    seller: CurrentSeller,
    session: Session,
) -> dict:
    product = await products.find_by_id(session, product_id)
    shop = await shops.find_by_owner(session, seller.id)

    # 404 for missing, for someone else's, and for "you have no shop" alike,
    # so the response cannot be used to discover which product ids exist.
    if product is None or shop is None or product.shop_id != shop.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )

    updated = await products.update_product(
        session,
        product,
        name=body.name,
        description=body.description,
        price=body.price,
        stock=body.stock,
        image_url=body.imageUrl,
        status=body.status,
        image_urls=body.imageUrls,
    )
    return _serialise(updated)


@router.get("/products/{product_id}")
async def get_product(product_id: str, session: Session) -> dict:
    """Public: the product detail screen, with its shop's origin and
    contact so the page can show where it ships from and estimate how long
    it will take."""
    product = await products.find_by_id(session, product_id)
    if product is None or product.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )
    shop = await shops.find_by_id(session, product.shop_id)
    average, count = await reviews.summary(session, product_id)
    return {
        **_serialise(product),
        "shopName": shop.name if shop else None,
        "shopAddress": shop.address if shop else None,
        "shopProvince": shop.province if shop else None,
        "shopPhone": shop.phone if shop else None,
        "ratingAverage": average,
        "ratingCount": count,
    }
