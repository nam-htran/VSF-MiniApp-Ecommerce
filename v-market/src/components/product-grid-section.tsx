import { Icon, Image, Typography, useNavigate } from '@v-miniapp/ui-react';
import { formatVnd } from '@/lib/format';
import { estimateDelivery } from '@/lib/delivery';
import type { ProductCardData } from '@/lib/product-card';
import { Skeleton } from '@v-miniapp/ui-react';


/** 1234 -> "1,2k", Shopee-style. */
const formatSold = (sold: number) =>
  sold >= 1000 ? `${(sold / 1000).toFixed(1).replace('.', ',')}k` : String(sold);

/**
 * Shopee-style two-column grid: image, name, price with the old price
 * struck through, then the rows buyers actually decide on — how long
 * shipping takes, which warehouse it ships from, how many sold. No add
 * button; the whole card opens the product once a detail page exists.
 */
export const ProductGridSection = ({
  products,
}: {
  /** undefined = loading (skeletons); [] = the marketplace is empty. */
  products?: ProductCardData[];
}) => {
  if (products === undefined) {
    return (
      <section className="grid grid-cols-2 gap-2 p-3">
        {[0, 1, 2, 3].map(i => (
          <div
            key={i}
            className="flex flex-col gap-1.5 rounded-xl bg-alias-background p-2 shadow-sm">
            <Skeleton className="h-36 w-full rounded-lg" />
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        ))}
      </section>
    );
  }

  if (products.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 px-8 py-16 text-center">
        <span className="text-5xl">🏪</span>
        <Typography size="large" weight="semibold">
          Sàn chưa có sản phẩm nào
        </Typography>
        <Typography size="small" color="text-secondary">
          Hãy quay lại sau, hoặc mở shop và đăng món hàng đầu tiên.
        </Typography>
      </div>
    );
  }

  return (
    <section className="grid grid-cols-2 gap-2 p-3">
      {products.map(product => (
        <GridProductCard key={product.id} product={product} />
      ))}
    </section>
  );
};

/** Exported for reuse — the search results render the same card. */
export const GridProductCard = ({ product }: { product: ProductCardData }) => {
  const navigate = useNavigate();
  // The card's delivery line comes from the shop's province when known
  // (real products); demo cards may still carry a hand-set shipDays.
  const eta = product.shipDays
    ? `Giao ${product.shipDays}`
    : product.shopProvince
      ? `Giao ${estimateDelivery(product.shopProvince).days}`
      : null;
  const hasRating = (product.ratingCount ?? 0) > 0;
  const hasSold = (product.sold ?? 0) > 0;
  return (
  <button
    type="button"
    // The whole card opens the detail page, carrying its data in
    // navigation state so the detail renders without a request.
    onClick={() =>
      navigate('/product', { params: { id: product.id }, state: { product } })
    }
    className="flex w-full flex-col gap-1.5 rounded-xl bg-alias-background p-2 text-left shadow-sm">
    <Image
      src={product.image}
      alt={product.name}
      fit="cover"
      // NOT lazy — same story as the flash strip: Image only sets src
      // after its internal VisibilitySensor fires, and inside the app's
      // scroll container it never does, so photos silently fall back to
      // the emoji. Bundled images are cheap; real lazy-loading returns
      // when products come from the backend, implemented by hand.
      className="h-36 w-full rounded-lg"
      // The emoji tile steps in if the photo fails, at the same size,
      // so the card never collapses and shifts the grid.
      fallback={
        <div
          className={`flex h-36 w-full items-center justify-center rounded-lg text-4xl ${product.tint}`}>
          {product.emoji}
        </div>
      }
    />

    <div className="flex flex-col">
      <Typography size="small" weight="bold" className="line-clamp-2">
        {product.name}
      </Typography>
      {product.unit && (
        <Typography size="2x-small" color="text-secondary" className="truncate">
          {product.unit}
        </Typography>
      )}
    </div>

    <div className="flex flex-wrap items-baseline gap-x-1.5">
      <Typography
        size="base"
        weight="bold"
        className={product.oldPrice ? 'text-global-red-red-60' : undefined}>
        {formatVnd(product.price)}
      </Typography>
      {product.oldPrice && (
        <Typography size="2x-small" color="text-tertiary" className="line-through">
          {formatVnd(product.oldPrice)}
        </Typography>
      )}
    </div>

    <div className="mt-auto flex flex-col gap-0.5">
      {(hasRating || hasSold) && (
        <div className="flex items-center gap-1">
          {hasRating && (
            <span className="flex items-center gap-0.5">
              <Icon name="star" type="fill" size={11} className="shrink-0 text-global-amber-amber-50" />
              <Typography size="2x-small" color="text-secondary">
                {(product.ratingAverage ?? 0).toFixed(1)}
              </Typography>
            </span>
          )}
          {hasRating && hasSold && (
            <Typography size="2x-small" color="text-tertiary">
              ·
            </Typography>
          )}
          {hasSold && (
            <Typography size="2x-small" color="text-tertiary">
              Đã bán {formatSold(product.sold ?? 0)}
            </Typography>
          )}
        </div>
      )}
      {eta && (
        <span className="flex min-w-0 items-center gap-1">
          <Icon name="scooter-front" size={12} className="shrink-0 text-global-teal-teal-60" />
          <Typography size="2x-small" color="text-secondary" className="truncate">
            {eta}
          </Typography>
        </span>
      )}
      {/* Demo rows carry a warehouse; real items name their shop. */}
      {(product.warehouse || product.shopName) && (
        <span className="flex min-w-0 items-center gap-1">
          <Icon name="pin" size={12} className="shrink-0 text-global-teal-teal-60" />
          <Typography size="2x-small" color="text-secondary" className="truncate">
            {product.warehouse ? `Kho ${product.warehouse}` : product.shopName}
          </Typography>
        </span>
      )}
    </div>
  </button>
  );
};
