import { useCallback } from 'react';
import { Icon, Typography } from '@v-miniapp/ui-react';
import { listOnSale, PRODUCT_PAGE } from '@/api/products';
import { ProductGridSection } from '@/components/product-grid-section';
import { usePagedProducts } from '@/lib/paged-feed';

/**
 * All the flash-sale items — the "see all" page behind the home strip.
 * Every discounted product across the catalogue, in the same card as the
 * storefront grid, scrolled through a page at a time.
 *
 * The demo catalogue has no seeded categories, so this page deliberately
 * stays as one continuous sale feed.
 */
const FlashSalePage = () => {
  const page = useCallback(
    (offset: number) => listOnSale(PRODUCT_PAGE, offset),
    []
  );
  const { feed, sentinel } = usePagedProducts(page);

  const products = feed.status === 'ready' ? feed.products : undefined;

  return (
    <div className="pt-chrome flex min-h-full flex-col gap-2 bg-alias-layer-01 pb-6">
      <div className="flex items-center gap-2 px-4">
        <Icon name="bolt" size={22} className="text-brand" />
        <Typography size="2x-large" weight="bold" component="h1">
          Flash sale
        </Typography>
        <span className="animate-pulse text-xl">🔥</span>
      </div>

      {products !== undefined && products.length === 0 ? (
        <div className="flex flex-col items-center gap-2 px-8 pt-12 text-center">
          <span className="text-4xl">🏷️</span>
          <Typography size="small" color="text-secondary">
            Chưa có sản phẩm giảm giá trong danh mục này.
          </Typography>
        </div>
      ) : (
        <ProductGridSection products={products} />
      )}

      {feed.status === 'ready' && feed.hasMore && (
        <div ref={sentinel} className="flex justify-center py-6">
          <Typography size="small" color="text-secondary">
            Đang tải thêm…
          </Typography>
        </div>
      )}
    </div>
  );
};

export default FlashSalePage;
