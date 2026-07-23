import { useEffect, useState } from 'react';
import { Icon, Typography } from '@v-miniapp/ui-react';
import { listOnSale, type ApiProductListItem } from '@/api/products';
import { ProductGridSection } from '@/components/product-grid-section';
import type { ProductCardData } from '@/lib/product-card';

const toCard = (item: ApiProductListItem): ProductCardData => ({
  id: item.id,
  name: item.name,
  description: item.description,
  unit: item.unit ?? undefined,
  price: item.price,
  oldPrice: item.originalPrice ?? undefined,
  image: item.imageUrl ?? undefined,
  shopId: item.shopId,
  shopName: item.shopName,
  shopProvince: item.shopProvince,
  ratingAverage: item.ratingAverage,
  ratingCount: item.ratingCount,
  sold: item.sold,
  emoji: '🛒',
  tint: 'bg-global-neutral-neutral-10',
});

/**
 * All the flash-sale items — the "see all" page behind the home strip.
 * Every discounted product across the catalogue, in the same card as the
 * storefront grid.
 */
const FlashSalePage = () => {
  const [products, setProducts] = useState<ProductCardData[] | undefined>();

  useEffect(() => {
    listOnSale(50)
      .then(page => setProducts(page.items.map(toCard)))
      .catch(() => setProducts([]));
  }, []);

  return (
    <div className="pt-chrome flex min-h-full flex-col bg-alias-layer-01 pb-6">
      <div className="flex items-center gap-2 px-4 py-2">
        <Icon name="bolt" size={22} className="text-brand" />
        <Typography size="2x-large" weight="bold" component="h1">
          Flash sale
        </Typography>
        <span className="animate-pulse text-xl">🔥</span>
      </div>
      <ProductGridSection products={products} />
    </div>
  );
};

export default FlashSalePage;
