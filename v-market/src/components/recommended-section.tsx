import { useEffect, useState } from 'react';
import { Skeleton, Typography } from '@v-miniapp/ui-react';
import {
  listRecommendations,
  type RecommendationSource,
} from '@/api/recommendations';
import { ProductStrip } from '@/components/product-strip';
import { useSession } from '@/lib/auth';
import { listItemToCard, type ProductCardData } from '@/lib/product-card';

/** What the strip is allowed to call itself. Products picked from the
 *  shopper's own browsing get the personal title; the best-seller fallback
 *  says what it is, because a popularity list is not personalisation. */
const TITLES: Record<RecommendationSource, string> = {
  transformer: 'Dành cho bạn',
  'semantic-id': 'Dành cho bạn',
  popular: 'Đang bán chạy',
};

type State =
  | { status: 'loading' }
  | { status: 'ready'; products: ProductCardData[]; source: RecommendationSource }
  | { status: 'hidden' };

/**
 * The recommendation strip under the flash sale.
 *
 * Signed-out shoppers see nothing at all — not an empty box and not a
 * prompt to log in. There is no history to recommend from, and the
 * storefront grid below already shows the whole catalogue.
 *
 * A failure hides the strip too. This is a suggestion, not content the
 * shopper asked for, so it fails silently rather than putting an error
 * where a nice-to-have used to be.
 */
export const RecommendedSection = () => {
  const session = useSession();
  const [state, setState] = useState<State>({ status: 'loading' });

  useEffect(() => {
    if (!session) {
      setState({ status: 'hidden' });
      return;
    }
    // Guards against a late response from a previous session landing after
    // the shopper has signed out or switched account.
    let alive = true;
    setState({ status: 'loading' });
    listRecommendations()
      .then(({ items, source }) => {
        if (!alive) return;
        setState(
          items.length === 0
            ? { status: 'hidden' }
            : { status: 'ready', products: items.map(listItemToCard), source }
        );
      })
      .catch(() => alive && setState({ status: 'hidden' }));
    return () => {
      alive = false;
    };
  }, [session]);

  if (state.status === 'hidden') return null;

  if (state.status === 'loading') {
    return (
      <div className="mx-3 flex flex-col gap-2 rounded-2xl bg-alias-background p-3.5 shadow-sm">
        <Typography size="base" weight="bold">
          {TITLES['semantic-id']}
        </Typography>
        <div className="flex gap-2 overflow-hidden">
          {[0, 1, 2].map(index => (
            <Skeleton key={index} className="h-44 w-36 shrink-0 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  return <ProductStrip title={TITLES[state.source]} products={state.products} />;
};
