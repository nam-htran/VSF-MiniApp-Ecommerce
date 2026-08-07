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
 * `source` says which route answered — "semantic-id" when the products come
 * from what the shopper has been looking at, "popular" when there was no
 * history to go on. The strip labels itself from it rather than claiming
 * personalisation it did not do.
 */
export type RecommendationSource = 'semantic-id' | 'popular';

export type Recommendations = {
  items: ApiProductListItem[];
  source: RecommendationSource;
};

export const listRecommendations = (limit = 10) =>
  apiRequest<Recommendations>(`/recommendations?limit=${limit}`, {
    headers: bearer(),
  });

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
