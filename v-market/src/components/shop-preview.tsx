import { useEffect, useState } from 'react';
import {
  Icon,
  Image,
  Skeleton,
  Typography,
  useNavigate,
} from '@v-miniapp/ui-react';
import { getShop, type Shop } from '@/api/shops';
import { listShopProducts } from '@/api/products';
import { GridProductCard } from '@/components/product-grid-section';
import { Stars } from '@/components/reviews-section';
import { listItemToCard, type ProductCardData } from '@/lib/product-card';

/**
 * The shop, on a product page — a small storefront rather than a row of
 * text: the seller's own banner and logo, their name and stats, then the
 * rest of what they sell. It is the same promise the shop page makes, in
 * card form, so tapping through feels like opening what you already saw.
 *
 * Owns its own fetches (the product detail carries a shop *name*, not a
 * banner), and renders nothing at all if the shop can't be loaded.
 */
export const ShopPreview = ({
  shopId,
  fallbackName,
  excludeProductId,
}: {
  shopId: string;
  /** Shown while the shop loads — the detail already knows the name. */
  fallbackName?: string;
  /** The product being viewed: it belongs in the page, not in its own
   *  "more from this shop" strip. */
  excludeProductId: string;
}) => {
  const navigate = useNavigate();
  const [shop, setShop] = useState<Shop | null | undefined>(undefined);
  const [products, setProducts] = useState<ProductCardData[]>([]);

  useEffect(() => {
    getShop(shopId)
      .then(setShop)
      .catch(() => setShop(null));
  }, [shopId]);

  useEffect(() => {
    listShopProducts(shopId, 12)
      .then(page =>
        setProducts(
          page.items.filter(p => p.id !== excludeProductId).map(listItemToCard)
        )
      )
      .catch(() => setProducts([]));
  }, [shopId, excludeProductId]);

  if (shop === undefined) {
    return (
      // Same geometry as the loaded card, so nothing shifts when it lands.
      <div className="mx-3 overflow-hidden rounded-2xl shadow-sm">
        <Skeleton className="h-36 w-full" />
      </div>
    );
  }
  if (shop === null) return null;

  // Averaged over the products that actually have ratings, so a shop full
  // of unrated items doesn't get dragged toward zero.
  const rated = products.filter(p => (p.ratingCount ?? 0) > 0);
  const rating = rated.length
    ? rated.reduce((sum, p) => sum + (p.ratingAverage ?? 0), 0) / rated.length
    : 0;

  return (
    <section className="mx-3 flex flex-col overflow-hidden rounded-2xl bg-alias-background shadow-sm">
      {/* Header is one button: banner, logo and name all open the shop, so
          there is nothing nested inside it to fight for the tap. */}
      {/* One hero: the seller's banner fills the whole header and the name
          sits on top of it, rather than in a white strip underneath — which
          left the logo stranded on the seam and the card looking lopsided. */}
      <button
        type="button"
        onClick={() => navigate('/shop', { params: { id: shop.id } })}
        className="relative block w-full text-left">
        <div
          className="h-36 w-full bg-brand bg-cover bg-center"
          style={
            shop.imageUrl
              ? { backgroundImage: `url("${shop.imageUrl}")` }
              : undefined
          }
        />
        {/* Darkest where the text lands, clear at the top, so the banner
            still reads as the seller's artwork. */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/30 to-transparent" />

        <div className="absolute inset-x-0 bottom-0 flex items-center gap-3 p-3.5">
          <span className="flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-2xl border-2 border-global-basic-white/80 bg-alias-background shadow-md">
            {shop.logoUrl ? (
              <Image src={shop.logoUrl} alt="" fit="cover" className="size-full" />
            ) : (
              <Icon name="office" size={24} className="text-brand" />
            )}
          </span>

          <div className="flex min-w-0 flex-1 flex-col">
            <Typography
              size="base"
              weight="bold"
              className="truncate text-global-basic-white">
              {shop.name || fallbackName}
            </Typography>
            <span className="flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-global-basic-white opacity-90">
              {rating > 0 && (
                <span className="flex items-center gap-1">
                  <Stars value={rating} />
                  <Typography size="2x-small" className="text-global-basic-white">
                    {rating.toFixed(1)}
                  </Typography>
                </span>
              )}
              <Typography size="2x-small" className="text-global-basic-white">
                {products.length + 1} sản phẩm
              </Typography>
              {shop.province && (
                <span className="flex min-w-0 items-center gap-1">
                  <Icon name="pin" size={11} className="shrink-0 text-global-basic-white" />
                  <Typography
                    size="2x-small"
                    className="truncate text-global-basic-white">
                    {shop.province}
                  </Typography>
                </span>
              )}
            </span>
          </div>

          <span className="flex shrink-0 items-center gap-0.5 rounded-full bg-alias-background py-1 pl-2.5 pr-1.5 shadow-sm">
            <Typography size="x-small" weight="semibold" className="text-brand">
              Xem shop
            </Typography>
            <Icon name="chevron-right" size={13} className="text-brand" />
          </span>
        </div>
      </button>

      {products.length > 0 && (
        // Tinted so the white product cards read as cards against it.
        <div className="flex flex-col gap-2 bg-alias-layer-01 px-3.5 py-3">
          <Typography size="small" weight="semibold">
            Sản phẩm khác của shop
          </Typography>
          <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
            {products.map(product => (
              <div key={product.id} className="w-36 shrink-0">
                <GridProductCard product={product} />
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
};
