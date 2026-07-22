import { useEffect, useState } from 'react';
import { Icon, Image, Typography, useNavigate } from '@v-miniapp/ui-react';
import { formatVnd } from '@/lib/format';
import type { ProductCardData } from '@/lib/product-card';
import imgChicken from '@/assets/products/chicken.jpg';
import imgEggs from '@/assets/products/eggs.jpg';
import imgBeef from '@/assets/products/beef.jpg';
import imgRice from '@/assets/products/rice.jpg';

/**
 * TEMPORARY demo content. There is no endpoint that lists products across
 * shops yet, and no discount model at all — replace this array with real
 * data when either exists.
 *
 * Photos are bundled, not hotlinked: an external image host cannot be
 * whitelisted (only domains we own can be), so remote URLs would break on
 * a device. Unsplash-licensed, downloaded into src/assets/products.
 */
/** Every flash item has a sale, so oldPrice is required here. */
type DemoProduct = ProductCardData & { oldPrice: number };

const DEMO_PRODUCTS: DemoProduct[] = [
  {
    id: '1',
    name: 'Ức gà đông lạnh',
    unit: '450–500g /gói',
    price: 56000,
    oldPrice: 80000,
    image: imgChicken,
    emoji: '🍗',
    tint: 'bg-global-orange-orange-10',
  },
  {
    id: '2',
    name: 'Trứng gà ta',
    unit: 'Hộp 12 quả',
    price: 32500,
    oldPrice: 50000,
    image: imgEggs,
    emoji: '🥚',
    tint: 'bg-global-stone-stone-10',
  },
  {
    id: '3',
    name: 'Thịt bò nấu súp',
    unit: '450–500g /gói',
    price: 75000,
    oldPrice: 93000,
    image: imgBeef,
    emoji: '🥩',
    tint: 'bg-global-rose-rose-10',
  },
  {
    id: '4',
    name: 'Gạo ST25',
    unit: 'Túi 5kg',
    price: 166500,
    oldPrice: 185000,
    image: imgRice,
    emoji: '🌾',
    tint: 'bg-global-emerald-emerald-10',
  },
];

const discountPercent = (product: DemoProduct) =>
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
 * "Flash sale" strip: header with a live countdown and a "see all" link,
 * then a horizontal row of compact white cards — photo with a discount
 * badge, name, unit, sale price with the old price struck through.
 *
 * No add-to-cart button on the cards: the goal is density, supermarket
 * style — the card itself will open the product once a detail page
 * exists.
 */
export const FlashSaleSection = ({
  products,
}: {
  /** Real discounted items; the demo array fills in until they load. */
  products?: ProductCardData[];
}) => {
  const countdown = useCountdown();
  // A flash item is defined by its old price — anything without one
  // cannot render a badge or a struck-through price, so it stays out.
  const items: DemoProduct[] = products?.length
    ? products.filter((p): p is DemoProduct => p.oldPrice !== undefined)
    : DEMO_PRODUCTS;

  return (
    <section className="flex flex-col gap-3 bg-global-teal-teal-10 px-4 pb-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Typography size="large" weight="bold" component="h2">
            Flash sale <span className="animate-pulse">🔥</span>
          </Typography>
          {/* The ticking clock is what makes the screen feel alive. */}
          <span className="flex items-center gap-1 rounded-lg bg-global-red-red-60 px-2 py-0.5">
            <Icon name="clock" size={12} className="text-global-basic-white" />
            <Typography
              size="x-small"
              weight="bold"
              className="text-global-basic-white tabular-nums">
              {countdown}
            </Typography>
          </span>
        </div>
        <button type="button" className="flex items-center gap-0.5">
          <Typography
            size="small"
            weight="semibold"
            className="text-global-teal-teal-60">
            Xem tất cả
          </Typography>
          <Icon name="chevron-right" size={16} className="text-global-teal-teal-60" />
        </button>
      </div>

      {/* Scrolls inside itself; the page never scrolls sideways. */}
      <div className="-mx-4 overflow-x-auto px-4">
        <div className="flex w-max gap-2 pb-1">
          {items.map(product => (
            <ProductCard key={product.id} product={product} />
          ))}
        </div>
      </div>
    </section>
  );
};

const ProductCard = ({ product }: { product: DemoProduct }) => {
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
        // Deliberately NOT lazy. Image only sets src after an internal
        // VisibilitySensor fires, and inside this horizontal scroller the
        // sensor never does — the photo silently falls back to the emoji.
        // Above-the-fold images should load eagerly anyway: this strip is
        // the LCP candidate.
        className="h-24 w-full rounded-lg"
        // The emoji tile steps in if the photo fails, at the same size,
        // so the card never collapses and shifts the row.
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
      <Typography size="2x-small" color="text-secondary" className="truncate">
        {product.unit}
      </Typography>
    </div>

    <div className="mt-auto flex flex-wrap items-baseline gap-x-1.5">
      <Typography
        size="small"
        weight="bold"
        className="text-global-red-red-60">
        {formatVnd(product.price)}
      </Typography>
      <Typography size="2x-small" color="text-tertiary" className="line-through">
        {formatVnd(product.oldPrice)}
      </Typography>
    </div>
  </button>
  );
};
