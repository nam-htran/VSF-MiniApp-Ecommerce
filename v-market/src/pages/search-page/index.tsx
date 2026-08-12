import { useCallback, useEffect, useState } from 'react';
import { Skeleton, Typography } from '@v-miniapp/ui-react';
import { listProducts, PRODUCT_PAGE } from '@/api/products';
import { GridProductCard } from '@/components/product-grid-section';
import { usePagedProducts } from '@/lib/paged-feed';
import { useSearchFilters, useSearchQuery } from '@/lib/search-query';

/** Long enough that a request goes out after the user pauses rather than on
 *  every keystroke. */
const TYPING_PAUSE = 300;

/**
 * Results only — the input lives in the top chrome, and the query arrives
 * through the shared store. The match runs on the server (?q=), so it
 * covers the whole catalogue rather than one page filtered on the client,
 * and it scrolls through every match rather than stopping at the first
 * screenful.
 *
 * Results are ranked like the storefront: the same browsing history orders
 * what the query matched.
 */
const SearchPage = () => {
  const query = useSearchQuery();
  const filters = useSearchFilters();
  const [settled, setSettled] = useState(query);

  useEffect(() => {
    const timer = setTimeout(() => setSettled(query), TYPING_PAUSE);
    return () => clearTimeout(timer);
  }, [query]);

  // Identifies the list: a new query is a new list, and the feed restarts.
  const page = useCallback(
    (offset: number) =>
      listProducts(
        PRODUCT_PAGE,
        offset,
        settled.trim() || undefined,
        filters
      ),
    [settled, filters]
  );
  const { feed, sentinel } = usePagedProducts(page);

  return (
    <div className="pt-chrome flex min-h-full flex-col gap-3 px-3 pb-6">
      {feed.status === 'loading' ? (
        <div className="grid grid-cols-2 gap-2">
          {[0, 1, 2, 3].map(i => (
            <Skeleton key={i} className="h-56 w-full rounded-2xl" />
          ))}
        </div>
      ) : feed.status === 'failed' || feed.products.length === 0 ? (
        <div className="flex flex-col items-center gap-2 px-8 pt-20 text-center">
          <span className="text-5xl">🔍</span>
          <Typography size="large" weight="semibold">
            Không tìm thấy sản phẩm nào
          </Typography>
          <Typography size="small" color="text-secondary">
            Thử từ khoá khác, ví dụ tên món hàng hoặc tên cửa hàng.
          </Typography>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2">
            {feed.products.map(product => (
              <GridProductCard key={product.id} product={product} />
            ))}
          </div>
          {feed.hasMore && (
            <div ref={sentinel} className="flex justify-center py-6">
              <Typography size="small" color="text-secondary">
                Đang tải thêm…
              </Typography>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default SearchPage;
