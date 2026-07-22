import { Icon, Image, Typography } from '@v-miniapp/ui-react';
import { formatVnd } from '@/lib/format';
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
type DemoProduct = {
  id: string;
  name: string;
  unit: string;
  price: number;
  oldPrice: number;
  image: string;
  emoji: string;
  tint: string;
};

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

/**
 * "Flash sale" row from the reference: a section header with a "see all"
 * link, then a horizontal strip where every product is its own white
 * card — photo with a red discount badge, name, unit, price with the old
 * price struck through, and a round add button.
 */
export const FlashSaleSection = () => (
  <section className="flex flex-col gap-3 bg-global-teal-teal-10 px-4 pb-4">
    <div className="flex items-center justify-between">
      <Typography size="large" weight="bold" component="h2">
        Flash sale 🔥
      </Typography>
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
      <div className="flex w-max gap-3 pb-1">
        {DEMO_PRODUCTS.map(product => (
          <ProductCard key={product.id} product={product} />
        ))}
      </div>
    </div>
  </section>
);

const ProductCard = ({ product }: { product: DemoProduct }) => (
  <div className="flex w-40 shrink-0 flex-col gap-2 rounded-2xl bg-alias-background p-3">
    <div className="relative">
      <Image
        src={product.image}
        alt={product.name}
        fit="cover"
        lazy
        className="h-32 w-full rounded-xl"
        // The emoji tile steps in if the photo fails, at the same size,
        // so the card never collapses and shifts the row.
        fallback={
          <div
            className={`flex h-32 w-full items-center justify-center rounded-xl text-5xl ${product.tint}`}>
            {product.emoji}
          </div>
        }
      />
      <span className="absolute right-2 top-2 rounded-lg bg-global-red-red-60 px-2 py-0.5">
        <Typography size="x-small" weight="bold" className="text-global-basic-white">
          {discountPercent(product)}%
        </Typography>
      </span>
    </div>

    <div className="flex flex-col gap-0.5">
      <Typography size="base" weight="bold" className="line-clamp-2">
        {product.name}
      </Typography>
      <Typography size="x-small" color="text-secondary">
        {product.unit}
      </Typography>
    </div>

    <div className="mt-auto flex items-center justify-between">
      <div className="flex flex-col">
        <Typography size="base" weight="bold">
          {formatVnd(product.price)}
        </Typography>
        <Typography
          size="x-small"
          color="text-tertiary"
          className="line-through">
          {formatVnd(product.oldPrice)}
        </Typography>
      </div>
      {/* Visual only until a cart exists. */}
      <button
        type="button"
        aria-label={`Thêm ${product.name} vào giỏ`}
        className="flex size-8 shrink-0 items-center justify-center rounded-full bg-global-teal-teal-60">
        <Icon name="plus" size={18} className="text-global-basic-white" />
      </button>
    </div>
  </div>
);
