import { apiRequest } from './client';

export type Shop = {
  id: string;
  ownerId: string;
  name: string;
  description: string;
  imageUrl: string | null;
  status: 'ACTIVE' | 'LOCKED';
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
