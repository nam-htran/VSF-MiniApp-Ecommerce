import { apiRequest } from './client';
import { currentToken } from '@/lib/auth';
import { rememberSeen } from '@/lib/seen';
import type { ApiProductListItem } from './products';

/**
 * Related products, and the browsing history behind the ranking.
 *
 * A view needs a session: it belongs to somebody.
 */

const bearer = (): Record<string, string> | undefined => {
  const token = currentToken();
  return token ? { Authorization: `Bearer ${token}` } : undefined;
};

/** Related products need no user session: the current product supplies the SID. */
export const listRelatedProducts = (productId: string, limit = 10) =>
  apiRequest<{ items: ApiProductListItem[] }>(
    `/products/${productId}/related?limit=${limit}`
  );

/**
 * Remember that this product was opened, on the device and — for a shopper
 * with an account — on the server too.
 *
 * The local copy is written first and always: the POST needs a session and
 * is refused without one, which used to mean a visitor browsing anonymously
 * built no history at all and was never recommended anything.
 *
 * Fire-and-forget: a lost view costs a little recommendation quality and
 * nothing else, so it must never delay or break the page the shopper asked
 * for. Nothing on screen is told either — a feed already fetched picks the
 * new order up when it is next asked for, on pull-to-refresh or app start.
 */
export const recordProductView = (productId: string): void => {
  rememberSeen(productId);
  void apiRequest(`/products/${productId}/view`, {
    method: 'POST',
    headers: bearer(),
  }).catch(() => {});
};
