import { useEffect, useState } from 'react';
import { Alert, Button } from '@v-miniapp/ui-react';
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
  shopId: item.shopId,
  shopName: item.shopName,
  shopProvince: item.shopProvince,
  ratingAverage: item.ratingAverage,
  ratingCount: item.ratingCount,
  sold: item.sold,
  emoji: '🛒',
  tint: 'bg-global-neutral-neutral-10',
});

type Feed =
  | { status: 'loading' }
  | { status: 'ready'; products: ProductCardData[] }
  | { status: 'failed'; message: string };

/**
 * The database is the only source: one fetch of GET /products feeds the
 * grid with everything and the flash strip with the discounted items.
 * While loading the sections show skeletons; on failure the page says so
 * and offers a retry instead of pretending with fake content.
 */
const HomePage = () => {
  const [feed, setFeed] = useState<Feed>({ status: 'loading' });

  const load = () => {
    setFeed({ status: 'loading' });
    listProducts()
      .then(page =>
        setFeed({ status: 'ready', products: page.items.map(toCard) })
      )
      .catch(error =>
        setFeed({
          status: 'failed',
          message: error instanceof Error ? error.message : String(error),
        })
      );
  };

  useEffect(load, []);

  const products =
    feed.status === 'ready' ? feed.products : undefined;

  return (
    <div className="flex flex-col">
      <PromoSection />
      {feed.status === 'failed' ? (
        <div className="p-4">
          <Alert
            type="negative"
            title="Không tải được sản phẩm"
            message={feed.message}
            action={<Button shape="pill" onClick={load}>Thử lại</Button>}
          />
        </div>
      ) : (
        <>
          <FlashSaleSection products={products} />
          <ProductGridSection products={products} />
        </>
      )}
    </div>
  );
};

export default HomePage;
