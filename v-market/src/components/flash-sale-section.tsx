import { useEffect, useState } from 'react';
import {
  Icon,
  Image,
  Skeleton,
  Typography,
  useNavigate,
} from '@v-miniapp/ui-react';
import { formatVnd } from '@/lib/format';
import type { ProductCardData } from '@/lib/product-card';

/** A flash item is defined by its old price — nothing else can render a
 * badge or a struck-through price. */
type FlashProduct = ProductCardData & { oldPrice: number };

const discountPercent = (product: FlashProduct) =>
  Math.round((1 - product.price / product.oldPrice) * 100);

/** hh:mm:ss until midnight — flash sales "end today", every day. */
const timeLeftToday = () => {
  const now = new Date();
  const midnight = new Date(now);
  midnight.setHours(24, 0, 0, 0);
  const total = Math.max(0, Math.floor((midnight.getTime() - now.getTime()) / 1000));
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${pad(Math.floor(total / 3600))}:${pad(Math.floor((total % 3600) / 60))}:${pad(total % 60)}`;
};

const useCountdown = () => {
  const [left, setLeft] = useState(timeLeftToday);
  useEffect(() => {
    const timer = setInterval(() => setLeft(timeLeftToday()), 1000);
    return () => clearInterval(timer);
  }, []);
  return left;
};

/**
 * "Flash sale" strip, fed exclusively by the backend — items with an
 * originalPrice. undefined = still loading → skeletons; an empty list
 * hides the strip entirely, because a flash sale with nothing in it is
 * not a section.
 */
export const FlashSaleSection = ({
  products,
}: {
  products?: ProductCardData[];
}) => {
  const countdown = useCountdown();
  const items = products?.filter(
    (p): p is FlashProduct => p.oldPrice !== undefined
  );

  if (items && items.length === 0) return null;

  return (
    <section className="flex flex-col gap-3 bg-brand px-4 pb-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Typography
            size="large"
            weight="bold"
            component="h2"
            className="text-global-basic-white">
            Flash sale <span className="animate-pulse">🔥</span>
          </Typography>
          {/* The ticking clock is what makes the screen feel alive. */}
          <span className="flex items-center gap-1 rounded-lg bg-global-basic-white px-2 py-0.5">
            <Icon name="clock" size={12} className="text-brand" />
            <Typography
              size="x-small"
              weight="bold"
              className="text-brand tabular-nums">
              {countdown}
            </Typography>
          </span>
        </div>
        <button type="button" className="flex items-center gap-0.5">
          <Typography
            size="small"
            weight="semibold"
            className="text-global-basic-white">
            Xem tất cả
          </Typography>
          <Icon name="chevron-right" size={16} className="text-global-basic-white" />
        </button>
      </div>

      {/* Scrolls inside itself; the page never scrolls sideways. */}
      <div className="-mx-4 overflow-x-auto px-4">
        <div className="flex w-max gap-2 pb-1">
          {items === undefined
            ? [0, 1, 2].map(i => <CardSkeleton key={i} />)
            : items.map(product => (
                <ProductCard key={product.id} product={product} />
              ))}
        </div>
      </div>
    </section>
  );
};

const ProductCard = ({ product }: { product: FlashProduct }) => {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      // The whole card opens the detail page, carrying its data in
      // navigation state so the detail renders without a request.
      onClick={() =>
        navigate('/product', { params: { id: product.id }, state: { product } })
      }
      className="flex w-32 shrink-0 flex-col gap-1.5 rounded-xl bg-alias-background p-2 text-left">
      <div className="relative">
        <Image
          src={product.image}
          alt={product.name}
          fit="cover"
          // NOT lazy — Image's internal VisibilitySensor never fires in
          // this app's scroll containers, and this strip is the LCP
          // candidate anyway. See platform-constraints §10.
          className="h-24 w-full rounded-lg"
          fallback={
            <div
              className={`flex h-24 w-full items-center justify-center rounded-lg text-4xl ${product.tint}`}>
              {product.emoji}
            </div>
          }
        />
        <span className="absolute right-1 top-1 rounded-md bg-global-red-red-60 px-1.5 py-0.5">
          <Typography size="2x-small" weight="bold" className="text-global-basic-white">
            -{discountPercent(product)}%
          </Typography>
        </span>
      </div>

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

      <div className="mt-auto flex flex-wrap items-baseline gap-x-1.5">
        <Typography size="small" weight="bold" className="text-global-red-red-60">
          {formatVnd(product.price)}
        </Typography>
        <Typography size="2x-small" color="text-tertiary" className="line-through">
          {formatVnd(product.oldPrice)}
        </Typography>
      </div>
    </button>
  );
};

// Same footprint as a real card, so the skeleton can never become the
// largest element and get locked in as LCP.
const CardSkeleton = () => (
  <div className="flex w-32 shrink-0 flex-col gap-1.5 rounded-xl bg-alias-background p-2">
    <Skeleton className="h-24 w-full rounded-lg" />
    <Skeleton className="h-4 w-3/4" />
    <Skeleton className="h-3 w-1/2" />
  </div>
);
