import { Icon, Image, Typography } from '@v-miniapp/ui-react';
import { formatVnd } from '@/lib/format';
import imgSauce from '@/assets/products/sauce.jpg';
import imgGreens from '@/assets/products/greens.jpg';
import imgMilk from '@/assets/products/milk.jpg';
import imgSalmon from '@/assets/products/salmon.jpg';
import imgBread from '@/assets/products/bread.jpg';
import imgApple from '@/assets/products/apple.jpg';

/**
 * TEMPORARY demo content, like the flash-sale strip — replace with a real
 * cross-shop product endpoint when one exists.
 *
 * Photos are bundled, not hotlinked (external hosts cannot be
 * whitelisted). Names follow the photos, not the other way round, and
 * carry no brand names — review rule 1.2.4 bans third-party trademarks.
 */
type DemoProduct = {
  id: string;
  name: string;
  unit: string;
  price: number;
  image: string;
  emoji: string;
  tint: string;
};

const DEMO_PRODUCTS: DemoProduct[] = [
  {
    id: '1',
    name: 'Sốt cà chua',
    unit: 'Hũ 300g',
    price: 42000,
    image: imgSauce,
    emoji: '🍅',
    tint: 'bg-global-red-red-10',
  },
  {
    id: '2',
    name: 'Salad rau củ tươi',
    unit: 'Hộp 400g',
    price: 35000,
    image: imgGreens,
    emoji: '🥬',
    tint: 'bg-global-lime-lime-10',
  },
  {
    id: '3',
    name: 'Sữa tươi nguyên chất',
    unit: 'Chai 1 lít',
    price: 38000,
    image: imgMilk,
    emoji: '🥛',
    tint: 'bg-global-sky-sky-10',
  },
  {
    id: '4',
    name: 'Cá hồi phi lê',
    unit: '200–250g /khay',
    price: 129000,
    image: imgSalmon,
    emoji: '🐟',
    tint: 'bg-global-rose-rose-10',
  },
  {
    id: '5',
    name: 'Bánh mì nguyên cám',
    unit: 'Ổ 400g',
    price: 45000,
    image: imgBread,
    emoji: '🍞',
    tint: 'bg-global-orange-orange-10',
  },
  {
    id: '6',
    name: 'Táo đỏ nhập khẩu',
    unit: 'Túi 1kg',
    price: 89000,
    image: imgApple,
    emoji: '🍎',
    tint: 'bg-global-red-red-10',
  },
];

/**
 * Two-column product grid on the page's own background — the mint block
 * ends with the flash-sale strip above it.
 */
export const ProductGridSection = () => (
  <section className="grid grid-cols-2 gap-3 p-4">
    {DEMO_PRODUCTS.map(product => (
      <ProductCard key={product.id} product={product} />
    ))}
  </section>
);

const ProductCard = ({ product }: { product: DemoProduct }) => (
  <div className="flex flex-col gap-2 rounded-2xl bg-alias-background p-3 shadow-sm">
    <Image
      src={product.image}
      alt={product.name}
      fit="cover"
      lazy
      className="h-32 w-full rounded-xl"
      // The emoji tile steps in if the photo fails, at the same size,
      // so the card never collapses and shifts the grid.
      fallback={
        <div
          className={`flex h-32 w-full items-center justify-center rounded-xl text-5xl ${product.tint}`}>
          {product.emoji}
        </div>
      }
    />

    <div className="flex flex-col gap-0.5">
      <Typography size="base" weight="bold" className="line-clamp-2">
        {product.name}
      </Typography>
      <Typography size="x-small" color="text-secondary">
        {product.unit}
      </Typography>
    </div>

    <div className="mt-auto flex items-center justify-between">
      <Typography size="base" weight="bold">
        {formatVnd(product.price)}
      </Typography>
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
