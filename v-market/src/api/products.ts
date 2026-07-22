import { apiRequest } from './client';

/** Shape returned by server/ — see server/app/products/routes.py. */
export type ApiProduct = {
  id: string;
  shopId: string;
  name: string;
  description: string;
  price: number;
  stock: number;
  imageUrl: string | null;
  status: 'ACTIVE' | 'HIDDEN';
};

/** Public — the product detail screen works without a session. */
export function getProduct(id: string) {
  return apiRequest<ApiProduct>(`/products/${id}`);
}
