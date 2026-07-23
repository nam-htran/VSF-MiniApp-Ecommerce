import { Typography } from '@v-miniapp/ui-react';
import { GridProductCard } from '@/components/product-grid-section';
import type { ProductCardData } from '@/lib/product-card';

/**
 * A horizontal strip of product cards — "more from this shop" and "similar
 * products" on the detail page. Reuses the same card as the home grid, so a
 * card in a strip shows exactly what one on the storefront does (rating,
 * sold, delivery, shop). Renders nothing when there is nothing to show.
 */
export const ProductStrip = ({
  title,
  products,
}: {
  title: string;
  products: ProductCardData[];
}) => {
  if (products.length === 0) return null;

  return (
    <div className="mx-3 flex flex-col gap-2 rounded-2xl bg-alias-background p-3.5 shadow-sm">
      <Typography size="base" weight="bold">
        {title}
      </Typography>
      <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
        {products.map(product => (
          <div key={product.id} className="w-36 shrink-0">
            <GridProductCard product={product} />
          </div>
        ))}
      </div>
    </div>
  );
};
