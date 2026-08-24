import { useSyncExternalStore } from 'react';
import type { IIconName } from '@v-miniapp/ui-react';
import type { OrderView } from '@/api/orders';

/**
 * Where an order has got to — the one question a buyer opens the app to
 * ask. Model B keeps two separate states (payment on the order, fulfilment
 * per shop); this folds both into the single word they look for.
 */
export type OrderStage =
  | 'pending'
  | 'processing'
  | 'shipping'
  | 'delivered'
  | 'cancelled';

export const orderStage = (order: OrderView): OrderStage => {
  if (order.status === 'CANCELLED' || order.status === 'FAILED')
    return 'cancelled';
  if (order.status === 'PENDING') return 'pending';
  // Cancelled slices are left out: a shop that called its part off is not
  // something still on its way, and counting it would pin an otherwise
  // fully delivered order at 'processing' for good.
  const shops = order.shopOrders.filter(s => s.status !== 'CANCELLED');
  if (shops.length === 0) return 'cancelled';
  if (shops.every(s => s.status === 'DELIVERED')) return 'delivered';
  if (shops.some(s => s.status === 'SHIPPING')) return 'shipping';
  return 'processing';
};

/**
 * The stages an order walks through, in the order it walks them — the
 * account tiles read as a journey because of it. 'cancelled' is absent on
 * purpose: it is an ending, not a step, and nothing is on its way.
 */
export const ORDER_STAGES: {
  stage: OrderStage;
  label: string;
  icon: IIconName;
}[] = [
  { stage: 'pending', label: 'Chờ thanh toán', icon: 'wallet' },
  { stage: 'processing', label: 'Chờ lấy hàng', icon: 'clipboard-list' },
  { stage: 'shipping', label: 'Đang giao', icon: 'scooter-front' },
  { stage: 'delivered', label: 'Đã giao', icon: 'badge-check' },
];

/**
 * Which stage /orders is showing. A module store rather than navigation
 * state because pages are kept alive: by the time the account tiles push
 * to /orders the list is already mounted, so a prop or a state initialiser
 * would never be read again. Same pattern as the search query.
 */
let showing: OrderStage | 'all' = 'all';
const listeners = new Set<() => void>();

export function showOrders(stage: OrderStage | 'all'): void {
  showing = stage;
  for (const listener of listeners) listener();
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

export function useOrdersShowing(): OrderStage | 'all' {
  return useSyncExternalStore(
    subscribe,
    () => showing,
    () => showing
  );
}
