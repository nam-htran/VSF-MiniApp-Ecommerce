import { useEffect, useState } from 'react';
import { listProducts, type ApiProductListItem } from '@/api/products';
import { FlashSaleSection } from '@/components/flash-sale-section';
import { ProductGridSection } from '@/components/product-grid-section';
import { PromoSection } from '@/components/promo-section';
import type { ProductCardData } from '@/lib/product-card';

const toCard = (item: ApiProductListItem): ProductCardData => ({
  id: item.id,
  name: item.name,
  description: item.description,
  unit: item.unit ?? undefined,
  price: item.price,
  oldPrice: item.originalPrice ?? undefined,
  image: item.imageUrl ?? undefined,
  shopName: item.shopName,
  emoji: '🛒',
  tint: 'bg-global-neutral-neutral-10',
});

/**
 * One fetch feeds both sections: the grid gets everything, the flash
 * strip gets the discounted items (originalPrice set). The demo arrays
 * only fill in while loading or when the backend is unreachable — a home
 * screen with content beats an empty one in a demo.
 */
const HomePage = () => {
  const [products, setProducts] = useState<ProductCardData[]>();

  useEffect(() => {
    listProducts()
      .then(page => {
        if (page.items.length) setProducts(page.items.map(toCard));
      })
      .catch(error => {
        console.warn('[home] product feed unavailable, keeping demo:', error);
      });
  }, []);

  const onSale = products?.filter(product => product.oldPrice !== undefined);

  return (
    <div className="flex flex-col">
      <PromoSection />
      <FlashSaleSection products={onSale} />
      <ProductGridSection products={products} />
    </div>
  );
};

export default HomePage;
