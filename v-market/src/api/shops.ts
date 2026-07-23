import { apiRequest } from './client';
import { currentToken } from '@/lib/auth';

export type Shop = {
  id: string;
  ownerId: string;
  name: string;
  description: string;
  imageUrl: string | null;
  status: 'ACTIVE' | 'LOCKED';
};

const bearer = (): Record<string, string> | undefined => {
  const token = currentToken();
  return token ? { Authorization: `Bearer ${token}` } : undefined;
};

export type ShopPage = {
  items: Shop[];
  hasMore: boolean;
};

/** Public — the home screen must work with no session. */
export function listShops(limit = 20, offset = 0) {
  return apiRequest<ShopPage>(`/shops?limit=${limit}&offset=${offset}`);
}

export function getShop(id: string) {
  return apiRequest<Shop>(`/shops/${id}`);
}

/** Seller-only: 403 (ApiError) when the caller has no shop — the "not a
 *  seller yet" state the seller screen shows an open-shop form for. */
export function getMyShop() {
  return apiRequest<Shop>('/shops/me', { headers: bearer() });
}

/** Open to any session — opening a shop is what grants the SELLER role. */
export function openShop(name: string, description: string) {
  return apiRequest<Shop>('/shops', {
    method: 'POST',
    data: { name, description },
    headers: bearer(),
  });
}
