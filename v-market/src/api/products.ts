import { apiRequest } from './client';
import { currentToken } from '@/lib/auth';

const bearer = (): Record<string, string> | undefined => {
  const token = currentToken();
  return token ? { Authorization: `Bearer ${token}` } : undefined;
};

/** Shape returned by server/ — see server/app/products/routes.py. */
export type ApiProduct = {
  id: string;
  shopId: string;
  name: string;
  description: string;
  unit: string | null;
  price: number;
  /** Set = on sale at `price`; this is the struck-through price. */
  originalPrice: number | null;
  stock: number;
  /** A category key — labels/emoji live on the client (lib/categories). */
  category: string | null;
  /** Cover image (first of the gallery), for the cards. */
  imageUrl: string | null;
  /** The full gallery the detail page swipes through. */
  imageUrls: string[];
  status: 'ACTIVE' | 'HIDDEN';
};

/** The detail screen also carries the shop's origin and contact, so it can
 *  show where the item ships from and estimate delivery time. */
export type ApiProductDetail = ApiProduct & {
  shopName: string | null;
  shopAddress: string | null;
  shopProvince: string | null;
  shopPhone: string | null;
  ratingAverage: number;
  ratingCount: number;
};

/** Public — the product detail screen works without a session. */
export function getProduct(id: string) {
  return apiRequest<ApiProductDetail>(`/products/${id}`);
}

/**
 * A storefront card carries more than the bare product: its shop's name and
 * province (for the delivery estimate), the average rating, and units sold.
 */
export type ApiProductListItem = ApiProduct & {
  shopName: string;
  shopProvince: string | null;
  ratingAverage: number;
  ratingCount: number;
  sold: number;
};

export type ProductPage = {
  items: ApiProductListItem[];
  hasMore: boolean;
};

/** Public — one shop's active products, for the "more from this shop" strip.
 *  Same enriched card data as the storefront feed. */
export function listShopProducts(shopId: string, limit = 10) {
  return apiRequest<{ items: ApiProductListItem[]; hasMore: boolean }>(
    `/shops/${shopId}/products?limit=${limit}`
  );
}

/**
 * Public — the storefront across every shop, no session needed. `q`
 * searches by product or shop name across the whole catalogue (server
 * side), not just the page fetched here.
 */
export function listProducts(limit = 20, offset = 0, q?: string) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (q && q.trim()) params.set('q', q.trim());
  return apiRequest<ProductPage>(`/products?${params.toString()}`);
}

/** Public — only discounted items, for the flash-sale "see all" page. */
export function listOnSale(limit = 50) {
  return apiRequest<ProductPage>(`/products?onSale=true&limit=${limit}`);
}

// --- Seller-facing (bearer required) ---

export type NewProduct = {
  name: string;
  description: string;
  unit?: string | null;
  price: number;
  originalPrice?: number | null;
  stock: number;
  category?: string | null;
  imageUrl?: string | null;
  imageUrls?: string[];
};

/** The seller's own products, hidden ones included. */
export function listMyProducts(limit = 50, offset = 0) {
  return apiRequest<{ items: ApiProduct[]; hasMore: boolean }>(
    `/products/mine?limit=${limit}&offset=${offset}`,
    { headers: bearer() }
  );
}

export function createProduct(body: NewProduct) {
  return apiRequest<ApiProduct>('/products', {
    method: 'POST',
    data: body,
    headers: bearer(),
  });
}

/** Partial update — including status ACTIVE/HIDDEN to show or hide. */
export function updateProduct(
  id: string,
  body: Partial<{
    name: string;
    description: string;
    price: number;
    stock: number;
    category: string | null;
    imageUrl: string | null;
    imageUrls: string[];
    status: 'ACTIVE' | 'HIDDEN';
  }>
) {
  return apiRequest<ApiProduct>(`/products/${id}`, {
    method: 'PATCH',
    data: body,
    headers: bearer(),
  });
}
