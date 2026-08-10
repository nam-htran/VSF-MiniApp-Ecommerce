import { apiRequest } from './client';
import { currentToken } from '@/lib/auth';
import type { ApiProductListItem } from './products';

/**
 * The "for you" strip, and the browsing history behind it.
 *
 * Both need a session: the server has nothing to personalise from without
 * a shopper, and a view belongs to somebody.
 */

const bearer = (): Record<string, string> | undefined => {
  const token = currentToken();
  return token ? { Authorization: `Bearer ${token}` } : undefined;
};

/**
 * `source` says whether the Transformer, SID fallback, or best-seller
 * fallback answered. The strip does not call popularity personalisation.
 */
export type RecommendationSource = 'transformer' | 'semantic-id' | 'popular';

export type Recommendations = {
  items: ApiProductListItem[];
  source: RecommendationSource;
};

export const listRecommendations = (limit = 10) =>
  apiRequest<Recommendations>(`/recommendations?limit=${limit}`, {
    headers: bearer(),
  });

/** Related products need no user session: the current product supplies the SID. */
export const listRelatedProducts = (productId: string, limit = 10) =>
  apiRequest<{ items: ApiProductListItem[] }>(
    `/products/${productId}/related?limit=${limit}`
  );

/**
 * Tell the server this product was opened. Fire-and-forget: a lost view
 * costs a little recommendation quality and nothing else, so it must never
 * delay or break the page the shopper actually asked for.
 */
export const recordProductView = (productId: string): void => {
  void apiRequest(`/products/${productId}/view`, {
    method: 'POST',
    headers: bearer(),
  }).catch(() => {});
};
