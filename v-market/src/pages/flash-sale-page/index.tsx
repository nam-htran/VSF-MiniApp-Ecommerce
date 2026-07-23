import { useEffect, useState } from 'react';
import { Icon, Typography } from '@v-miniapp/ui-react';
import { listOnSale, type ApiProductListItem } from '@/api/products';
import { CategoryRow } from '@/components/category-row';
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
  category: item.category,
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
  const [category, setCategory] = useState<string | 'all'>('all');

  useEffect(() => {
    listOnSale(50)
      .then(page => setProducts(page.items.map(toCard)))
      .catch(() => setProducts([]));
  }, []);

  const filtered =
    products === undefined
      ? undefined
      : category === 'all'
        ? products
        : products.filter(p => p.category === category);

  return (
    <div className="pt-chrome flex min-h-full flex-col gap-2 bg-alias-layer-01 pb-6">
      <div className="flex items-center gap-2 px-4 py-2">
        <Icon name="bolt" size={22} className="text-brand" />
        <Typography size="2x-large" weight="bold" component="h1">
          Flash sale
        </Typography>
        <span className="animate-pulse text-xl">🔥</span>
      </div>

      <CategoryRow value={category} onChange={setCategory} />

      {filtered !== undefined && filtered.length === 0 ? (
        <div className="flex flex-col items-center gap-2 px-8 pt-12 text-center">
          <span className="text-4xl">🏷️</span>
          <Typography size="small" color="text-secondary">
            Chưa có sản phẩm giảm giá trong danh mục này.
          </Typography>
        </div>
      ) : (
        <ProductGridSection products={filtered} />
      )}
    </div>
  );
};

export default FlashSalePage;
