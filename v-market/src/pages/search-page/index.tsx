import { useEffect, useState } from 'react';
import { Skeleton, Typography } from '@v-miniapp/ui-react';
import { listProducts, type ApiProductListItem } from '@/api/products';
import { GridProductCard } from '@/components/product-grid-section';
import { useSearchQuery } from '@/lib/search-query';
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
  emoji: '🛒',
  tint: 'bg-global-neutral-neutral-10',
});

/**
 * Results only — the input lives in the top chrome, and the query arrives
 * through the shared store. The match runs on the server (?q=), so it
 * covers the whole catalogue rather than one page filtered on the client.
 * Typing is debounced so a request goes out after the user pauses, not on
 * every keystroke.
 */
const SearchPage = () => {
  const query = useSearchQuery();
  // null = loading (first load or a pending debounce).
  const [results, setResults] = useState<ProductCardData[] | null>(null);

  useEffect(() => {
    let alive = true;
    setResults(null);
    const timer = setTimeout(() => {
      listProducts(50, 0, query.trim() || undefined)
        .then(page => alive && setResults(page.items.map(toCard)))
        .catch(() => alive && setResults([]));
    }, 300);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [query]);

  return (
    <div className="pt-chrome flex min-h-full flex-col gap-3 px-3 pb-6">
      {results === null ? (
        <div className="grid grid-cols-2 gap-2">
          {[0, 1, 2, 3].map(i => (
            <Skeleton key={i} className="h-56 w-full rounded-2xl" />
          ))}
        </div>
      ) : results.length === 0 ? (
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
        <div className="grid grid-cols-2 gap-2">
          {results.map(product => (
            <GridProductCard key={product.id} product={product} />
          ))}
        </div>
      )}
    </div>
  );
};

export default SearchPage;
