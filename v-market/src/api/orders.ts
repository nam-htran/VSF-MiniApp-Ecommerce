import { apiRequest } from './client';
import { currentToken } from '@/lib/auth';

/**
 * Orders — the one part of the shop that needs a session. The client
 * sends product ids and quantities only; every price is re-read on the
 * server inside the transaction that locks stock, so a stale cart can
 * never buy at yesterday's numbers. See server/app/orders/routes.py.
 */
export type OrderItemView = {
  productId: string;
  name: string;
  unit: string | null;
  price: number;
  qty: number;
  imageUrl: string | null;
};

/** One shop's slice of an order — fulfilment status lives here, per shop. */
export type ShopOrderView = {
  id: string;
  shopId: string;
  shopName: string;
  status: 'CONFIRMED' | 'SHIPPING' | 'DELIVERED' | 'CANCELLED';
  subtotal: number;
  /** Itemised, not folded into the total — review rule 5.2.1. */
  shippingFee: number;
  items: OrderItemView[];
};

export type OrderView = {
  id: string;
  /** Payment state, separate from each shop's fulfilment state. */
  status: 'PENDING' | 'PAID' | 'FAILED' | 'CANCELLED';
  address: string;
  total: number;
  createdAt: string;
  shopOrders: ShopOrderView[];
};

export type CheckoutItem = { productId: string; qty: number };

/**
 * Flat per-shop shipping, mirroring server/app/orders/store.py for the
 * checkout breakdown only. The server is authoritative — it recomputes
 * the total on POST /orders; this constant just lets the buyer see the
 * charge before confirming (review rule 5.2.1).
 */
export const SHIPPING_FEE_PER_SHOP = 15000;

// Every orders endpoint is behind CurrentUser. The token is attached here
// rather than in the transport, which stays unaware of sessions; the
// caller has already ensured a session exists (route guard or a check at
// the checkout button), so a missing token means the server answers 401.
const bearer = (): Record<string, string> | undefined => {
  const token = currentToken();
  return token ? { Authorization: `Bearer ${token}` } : undefined;
};

export function placeOrder(address: string, items: CheckoutItem[]) {
  return apiRequest<OrderView>('/orders', {
    method: 'POST',
    data: { address, items },
    headers: bearer(),
  });
}

export function listOrders(limit = 20, offset = 0) {
  return apiRequest<{ items: OrderView[]; hasMore: boolean }>(
    `/orders?limit=${limit}&offset=${offset}`,
    { headers: bearer() }
  );
}

export function getOrder(id: string) {
  return apiRequest<OrderView>(`/orders/${id}`, { headers: bearer() });
}

// --- Seller side: fulfilment. Only the owner of the shop sees these; the
// server scopes every call to the caller's own shop (AUTH-05). ---

/** One incoming slice as the seller sees it — its own fulfilment status
 *  plus the buyer's delivery address and date, which shipping needs. */
export type SellerShopOrder = {
  id: string;
  orderId: string;
  status: ShopOrderView['status'];
  subtotal: number;
  shippingFee: number;
  address: string;
  createdAt: string;
  items: OrderItemView[];
};

export type FulfilStatus = 'CONFIRMED' | 'SHIPPING' | 'DELIVERED';

export function listShopOrders(
  status?: ShopOrderView['status'],
  limit = 20,
  offset = 0
) {
  const query = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (status) query.set('status', status);
  return apiRequest<{ items: SellerShopOrder[]; hasMore: boolean }>(
    `/orders/shop?${query.toString()}`,
    { headers: bearer() }
  );
}

/** Walk one slice forward: CONFIRMED→SHIPPING→DELIVERED. The server
 *  accepts only the one legal next step. */
export function advanceShopOrder(
  shopOrderId: string,
  status: 'SHIPPING' | 'DELIVERED'
) {
  return apiRequest<SellerShopOrder>(`/orders/shop/${shopOrderId}`, {
    method: 'PATCH',
    data: { status },
    headers: bearer(),
  });
}
