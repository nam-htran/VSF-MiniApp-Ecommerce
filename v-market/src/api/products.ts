import { apiRequest } from './client';
import { currentToken } from '@/lib/auth';
import { seenProducts } from '@/lib/seen';

const bearer = (): Record<string, string> | undefined => {
  const token = currentToken();
  return token ? { Authorization: `Bearer ${token}` } : undefined;
};

/** Shape returned by server/ — see server/app/products/routes.py. */
export type ApiProduct = {
  id: string;
  shopId: string;
  /** The seller's article number. Unique inside their shop, not across
   *  the marketplace — two shops may both use "AO-001". */
  sku: string | null;
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
  /**
   * `price` after the best voucher running right now, and which voucher did
   * it. Computed server-side by the same code that discounts the order, so
   * this figure is what actually gets charged — never recompute it here.
   * Equal to `price` when no voucher applies.
   */
  effectivePrice: number;
  voucher: ProductVoucher | null;
  /** Empty = no options; `stock` above is then the product's own. When
   *  options exist, `stock` is their total. */
  variants: ApiVariant[];
};

/**
 * One buyable combination — "Đen / L" — with its own stock.
 *
 * Empty list = a plain product, stock lives on the product itself. When
 * options exist the buyer must pick one; the server refuses a line that
 * doesn't, rather than guessing a size.
 */
export type ApiVariant = {
  id: string;
  /** {"Màu sắc": "Đen", "Size": "L"} — the seller names the groups. */
  options: Record<string, string>;
  /** "Đen / L", already joined server-side. */
  label: string;
  /** null = sells at the product's price. */
  price: number | null;
  stock: number;
  imageUrl: string | null;
};

export type ProductVoucher = {
  code: string;
  description: string;
  /** Đồng taken off one unit. */
  discount: number;
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
  reactionCount?: number;
  commentCount?: number;
  reactedByMe?: boolean;
  reactionType?: 'LIKE' | 'LOVE' | 'HAHA' | 'WOW' | 'SAD' | null;
};

export type ProductPage = {
  items: ApiProductListItem[];
  hasMore: boolean;
  /** Which route ordered this page — null for a request with no session.
   *  Nothing renders it; an order cannot show its own reasoning, so this is
   *  how you tell a Transformer answer from a best-seller fallback. */
  rankedBy: 'transformer' | 'semantic-id' | 'popular' | null;
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
 *
 * The token, when there is one, only changes the order — the server ranks
 * this feed from what the shopper has been looking at. Without a token the
 * device's own history is sent instead, so a visitor with no account is
 * still recommended to.
 */
/** How much of the storefront one request carries. Not a ceiling on what a
 *  page may show — callers keep asking with a larger offset until `hasMore`
 *  says there is nothing left. Named so the pages that scroll through the
 *  catalogue and the request that serves them agree on one number. */
export const PRODUCT_PAGE = 20;

export async function listProducts(
  limit = PRODUCT_PAGE,
  offset = 0,
  q?: string
) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (q && q.trim()) params.set('q', q.trim());

  const headers = bearer();
  if (!headers) {
    // Only signed out: with a session the server has the history already,
    // and its own copy is the one that counts.
    const seen = await seenProducts();
    if (seen.length > 0) params.set('seen', seen.join(','));
  }
  return apiRequest<ProductPage>(`/products?${params.toString()}`, { headers });
}

/** Public — only discounted items, for the flash-sale strip and its "see
 *  all" page. Paged like the storefront: the strip shows the first page,
 *  the page behind it scrolls through the rest. */
export function listOnSale(limit = PRODUCT_PAGE, offset = 0) {
  return apiRequest<ProductPage>(
    `/products?onSale=true&limit=${limit}&offset=${offset}`
  );
}


// --- Seller-facing (bearer required) ---

export type NewProduct = {
  sku?: string | null;
  name: string;
  description: string;
  unit?: string | null;
  price: number;
  originalPrice?: number | null;
  stock: number;
  category?: string | null;
  imageUrl?: string | null;
  imageUrls?: string[];
  /** Omitted = a plain product, stock stays on the product. Sent on update
   *  it replaces the whole set, so an empty list removes the options. */
  variants?: DraftVariantPayload[];
};

/** What the seller's form sends for one combination. */
export type DraftVariantPayload = {
  options: Record<string, string>;
  stock: number;
  price?: number | null;
  imageUrl?: string | null;
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
    sku: string | null;
    name: string;
    description: string;
    price: number;
    stock: number;
    category: string | null;
    imageUrl: string | null;
    imageUrls: string[];
    status: 'ACTIVE' | 'HIDDEN';
    /** Sent = replace the whole set; an empty list removes the options and
     *  hands stock back to the product's own figure. Omit to leave alone. */
    variants: DraftVariantPayload[];
  }>
) {
  return apiRequest<ApiProduct>(`/products/${id}`, {
    method: 'PATCH',
    data: body,
    headers: bearer(),
  });
}

/**
 * Remove one of the seller's own products. The server really deletes it if
 * it was never ordered, and archives it if it was — either way it leaves
 * the shop. `outcome` says which, so the UI can word the confirmation
 * ("đã xoá" vs "đã lưu trữ", since a past buyer's order still shows it).
 */
export function deleteProduct(id: string) {
  return apiRequest<{ outcome: 'deleted' | 'archived' }>(`/products/${id}`, {
    method: 'DELETE',
    headers: bearer(),
  });
}
