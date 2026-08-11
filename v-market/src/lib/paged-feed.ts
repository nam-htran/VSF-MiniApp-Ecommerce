import { useCallback, useEffect, useRef, useState } from 'react';
import type { ProductPage } from '@/api/products';
import { listItemToCard, type ProductCardData } from './product-card';

/**
 * A product list that grows as it is scrolled, with no ceiling on where it
 * stops — it keeps asking for the next page until the server says there is
 * nothing left.
 *
 * Shared by the storefront, search and flash sale because the awkward parts
 * are the same in all three: not firing a second request while the first is
 * in flight, appending rather than replacing, and fetching the next page
 * before the shopper reaches the bottom rather than after.
 *
 * Paging is only correct because the order is stable across requests. The
 * server holds a ranking for the length of a walk, so a product cannot
 * shift across a page boundary and arrive twice, or never.
 *
 * `page` must be memoised: it identifies the list, so a new one restarts
 * from the top. That is what makes a search re-run when the query changes.
 */
export type PagedFeed =
  | { status: 'loading' }
  | { status: 'ready'; products: ProductCardData[]; hasMore: boolean }
  | { status: 'failed'; message: string };

export const usePagedProducts = (
  page: (offset: number) => Promise<ProductPage>
) => {
  const [feed, setFeed] = useState<PagedFeed>({ status: 'loading' });
  // Guards the fetch, not the render: the sentinel can cross the viewport
  // several times before a page lands.
  const fetching = useRef(false);
  const sentinel = useRef<HTMLDivElement | null>(null);

  const firstPage = useCallback(
    () =>
      page(0).then(result => ({
        status: 'ready' as const,
        products: result.items.map(listItemToCard),
        hasMore: result.hasMore,
      })),
    [page]
  );

  /** Skeletons, then the first page — or the error, with nothing on screen
   *  to protect. */
  const load = useCallback(() => {
    setFeed({ status: 'loading' });
    firstPage()
      .then(setFeed)
      .catch(error =>
        setFeed({
          status: 'failed',
          message: error instanceof Error ? error.message : String(error),
        })
      );
  }, [firstPage]);

  /** Back to page one without the skeletons, for pull-to-refresh. Returns
   *  the promise so a spinner can wait on it. */
  const refresh = useCallback(() => firstPage().then(setFeed), [firstPage]);

  const loadMore = useCallback(() => {
    if (feed.status !== 'ready' || !feed.hasMore || fetching.current) return;
    fetching.current = true;
    page(feed.products.length)
      .then(result =>
        setFeed(current =>
          current.status === 'ready'
            ? {
                ...current,
                products: [
                  ...current.products,
                  ...result.items.map(listItemToCard),
                ],
                hasMore: result.hasMore,
              }
            : current
        )
      )
      // Silent: there is a screen full of products either way, and the next
      // scroll tries again.
      .catch(() => {})
      .finally(() => {
        fetching.current = false;
      });
  }, [feed, page]);

  useEffect(load, [load]);

  // rootMargin fetches while the marker is still below the fold, so the next
  // products are usually there by the time the shopper scrolls to them.
  useEffect(() => {
    const node = sentinel.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      entries => entries.some(entry => entry.isIntersecting) && loadMore(),
      { rootMargin: '600px' }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [loadMore]);

  return { feed, load, refresh, sentinel };
};
