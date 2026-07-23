import { useEffect, useMemo, useState } from 'react';
import { Typography } from '@v-miniapp/ui-react';
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
  shopName: item.shopName,
  emoji: '🛒',
  tint: 'bg-global-neutral-neutral-10',
});

/**
 * Results only — the input lives in the top chrome, in the same spot as
 * the search pill on every other page, and the query arrives through the
 * shared store.
 *
 * Honest about its limits: one page of 50, name/shop substring match.
 * The seam for a real backend search (?q=) is the single fetch below.
 */
const SearchPage = () => {
  const query = useSearchQuery();
  const [all, setAll] = useState<ProductCardData[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    listProducts(50)
      .then(page => setAll(page.items.map(toCard)))
      .catch(() => setAll([]))
      .finally(() => setLoaded(true));
  }, []);

  const results = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return all;
    return all.filter(
      product =>
        product.name.toLowerCase().includes(needle) ||
        (product.shopName ?? '').toLowerCase().includes(needle)
    );
  }, [all, query]);

  return (
    <div className="pt-chrome flex min-h-full flex-col gap-3 px-3 pb-6">
      {loaded && results.length === 0 ? (
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
