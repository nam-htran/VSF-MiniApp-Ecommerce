import { Image, Typography, useNavigate } from '@v-miniapp/ui-react';
import { formatVnd } from '@/lib/format';
import type { ProductCardData } from '@/lib/product-card';

/**
 * A horizontal strip of compact product cards — "more from this shop" and
 * "similar products" on the detail page. Each card opens its product,
 * carrying its data in navigation state for an instant first paint. Renders
 * nothing when there is nothing to show.
 */
export const ProductStrip = ({
  title,
  products,
}: {
  title: string;
  products: ProductCardData[];
}) => {
  const navigate = useNavigate();
  if (products.length === 0) return null;

  return (
    <div className="mx-3 flex flex-col gap-2 rounded-2xl bg-alias-background p-3.5 shadow-sm">
      <Typography size="base" weight="bold">
        {title}
      </Typography>
      <div className="-mx-1 flex gap-3 overflow-x-auto px-1 pb-1">
        {products.map(product => (
          <button
            key={product.id}
            type="button"
            onClick={() =>
              navigate('/product', {
                params: { id: product.id },
                state: { product },
              })
            }
            className="flex w-28 shrink-0 flex-col gap-1 text-left">
            <Image
              src={product.image}
              alt={product.name}
              fit="cover"
              className="h-28 w-28 rounded-lg"
              fallback={
                <div
                  className={`flex h-28 w-28 items-center justify-center rounded-lg text-3xl ${product.tint}`}>
                  {product.emoji}
                </div>
              }
            />
            <Typography size="x-small" className="line-clamp-2">
              {product.name}
            </Typography>
            <Typography size="small" weight="bold" className="text-brand">
              {formatVnd(product.price)}
            </Typography>
          </button>
        ))}
      </div>
    </div>
  );
};
