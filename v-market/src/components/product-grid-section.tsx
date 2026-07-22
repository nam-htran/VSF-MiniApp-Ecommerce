import { Icon, Image, Typography, useNavigate } from '@v-miniapp/ui-react';
import { formatVnd } from '@/lib/format';
import type { ProductCardData } from '@/lib/product-card';
import imgSauce from '@/assets/products/sauce.jpg';
import imgGreens from '@/assets/products/greens.jpg';
import imgMilk from '@/assets/products/milk.jpg';
import imgSalmon from '@/assets/products/salmon.jpg';
import imgBread from '@/assets/products/bread.jpg';
import imgApple from '@/assets/products/apple.jpg';

/**
 * TEMPORARY demo content, like the flash-sale strip — replace with a real
 * cross-shop product endpoint when one exists. Shipping days, warehouse
 * and sold counts are invented until orders and inventory carry them.
 *
 * Photos are bundled, not hotlinked (external hosts cannot be
 * whitelisted). Names follow the photos, not the other way round, and
 * carry no brand names — review rule 1.2.4 bans third-party trademarks.
 */
/** Grid items always carry the Shopee rows, so those are required here. */
type DemoProduct = ProductCardData & {
  shipDays: string;
  warehouse: string;
  sold: number;
};

const DEMO_PRODUCTS: DemoProduct[] = [
  {
    id: '1',
    name: 'Sốt cà chua',
    unit: 'Hũ 300g',
    price: 42000,
    oldPrice: 52000,
    shipDays: '1–2 ngày',
    warehouse: 'Long Biên, Hà Nội',
    sold: 1243,
    image: imgSauce,
    emoji: '🍅',
    tint: 'bg-global-red-red-10',
  },
  {
    id: '2',
    name: 'Salad rau củ tươi',
    unit: 'Hộp 400g',
    price: 35000,
    shipDays: 'trong ngày',
    warehouse: 'Gia Lâm, Hà Nội',
    sold: 862,
    image: imgGreens,
    emoji: '🥬',
    tint: 'bg-global-lime-lime-10',
  },
  {
    id: '3',
    name: 'Sữa tươi nguyên chất',
    unit: 'Chai 1 lít',
    price: 38000,
    oldPrice: 45000,
    shipDays: '1–2 ngày',
    warehouse: 'Thủ Đức, TP.HCM',
    sold: 3521,
    image: imgMilk,
    emoji: '🥛',
    tint: 'bg-global-sky-sky-10',
  },
  {
    id: '4',
    name: 'Cá hồi phi lê',
    unit: '200–250g /khay',
    price: 129000,
    oldPrice: 155000,
    shipDays: 'trong ngày',
    warehouse: 'Cầu Giấy, Hà Nội',
    sold: 428,
    image: imgSalmon,
    emoji: '🐟',
    tint: 'bg-global-rose-rose-10',
  },
  {
    id: '5',
    name: 'Bánh mì nguyên cám',
    unit: 'Ổ 400g',
    price: 45000,
    shipDays: 'trong ngày',
    warehouse: 'Hoàn Kiếm, Hà Nội',
    sold: 2107,
    image: imgBread,
    emoji: '🍞',
    tint: 'bg-global-orange-orange-10',
  },
  {
    id: '6',
    name: 'Táo đỏ nhập khẩu',
    unit: 'Túi 1kg',
    price: 89000,
    oldPrice: 105000,
    shipDays: '2–3 ngày',
    warehouse: 'Bình Thạnh, TP.HCM',
    sold: 5934,
    image: imgApple,
    emoji: '🍎',
    tint: 'bg-global-red-red-10',
  },
];

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
  /** Real items from the backend; the demo array fills in until they load. */
  products?: ProductCardData[];
}) => (
  <section className="grid grid-cols-2 gap-2 p-3">
    {(products ?? DEMO_PRODUCTS).map(product => (
      <ProductCard key={product.id} product={product} />
    ))}
  </section>
);

const ProductCard = ({ product }: { product: ProductCardData }) => {
  const navigate = useNavigate();
  return (
  <button
    type="button"
    // The whole card opens the detail page, carrying its data in
    // navigation state so the detail renders without a request.
    onClick={() =>
      navigate('/product', { params: { id: product.id }, state: { product } })
    }
    className="flex flex-col gap-1.5 rounded-xl bg-alias-background p-2 text-left shadow-sm">
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
      {(product.shipDays || product.sold !== undefined) && (
        <div className="flex items-center justify-between gap-1">
          {product.shipDays && (
            <span className="flex min-w-0 items-center gap-1">
              <Icon name="scooter-front" size={12} className="shrink-0 text-global-teal-teal-60" />
              <Typography size="2x-small" color="text-secondary" className="truncate">
                Giao {product.shipDays}
              </Typography>
            </span>
          )}
          {product.sold !== undefined && (
            <Typography size="2x-small" color="text-tertiary" className="shrink-0">
              Đã bán {formatSold(product.sold)}
            </Typography>
          )}
        </div>
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
