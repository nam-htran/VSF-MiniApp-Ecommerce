import { useCallback } from 'react';
import {
  Alert,
  Button,
  PullToRefresh,
  Toast,
  Typography,
} from '@v-miniapp/ui-react';
import { listProducts, PRODUCT_PAGE } from '@/api/products';
import { FlashSaleSection } from '@/components/flash-sale-section';
import { ProductGridSection } from '@/components/product-grid-section';
import { PromoSection } from '@/components/promo-section';
import { usePagedProducts } from '@/lib/paged-feed';

/**
 * The storefront, a page at a time. The grid draws one page, then asks for
 * the next when the shopper nears the bottom, and keeps going for as long
 * as the server says there is more — no ceiling on how far it scrolls. It
 * does not fetch the marketplace before showing any of it: at two thousand
 * products that was forty requests before the first card appeared.
 *
 * The grid is the recommendation. There is no strip beside it: the server
 * ranks this feed from what the shopper has been looking at, so opening a
 * product reorders the marketplace itself.
 *
 * Pull down to refresh — only here, the storefront. Other tabs (cart,
 * orders, account) reload on their own actions and a pull there would
 * mean nothing, so PullToRefresh wraps this page alone. It is also where a
 * new ranking is picked up: `keepAlive` keeps this page mounted behind the
 * product being read, so nothing refetches on its own.
 */
const HomePage = () => {
  const page = useCallback(
    (offset: number) => listProducts(PRODUCT_PAGE, offset),
    []
  );
  const { feed, load, refresh, sentinel } = usePagedProducts(page);

  const onRefresh = () =>
    refresh().catch(() =>
      Toast.show({
        type: 'negative',
        message: 'Không làm mới được, thử lại sau',
        position: 'bottom',
      })
    );

  return (
    <PullToRefresh
      onRefresh={onRefresh}
      pullingText="Kéo xuống để làm mới"
      canReleaseText="Thả ra để làm mới"
      refreshingText="Đang làm mới…"
      completeText="Đã cập nhật">
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
            <FlashSaleSection />
            <ProductGridSection
              products={feed.status === 'ready' ? feed.products : undefined}
            />
            {feed.status === 'ready' && feed.hasMore && (
              <div ref={sentinel} className="flex justify-center py-6">
                <Typography size="small" color="text-secondary">
                  Đang tải thêm…
                </Typography>
              </div>
            )}
          </>
        )}
      </div>
    </PullToRefresh>
  );
};

export default HomePage;
