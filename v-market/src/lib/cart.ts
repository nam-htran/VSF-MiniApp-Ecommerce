import { useSyncExternalStore } from 'react';
import { loadJson, saveJson } from './storage';
import type { ProductCardData } from './product-card';

/**
 * The cart lives on the device, not in the backend: browsing and adding
 * to cart must work with no session (review rule 3.4.8 — the app serves
 * unidentified users). Login gates checkout, where the server re-checks
 * price and stock anyway — a client-side snapshot is display data, never
 * the source of truth for money.
 *
 * A module store rather than React context: app-level Layouts wrap each
 * page separately, so a context provider there would give every page its
 * own instance. One module, one state, every page sees the same cart.
 */
export type CartLine = {
  product: ProductCardData;
  qty: number;
};

const STORAGE_KEY = 'cart.v1';

let lines: CartLine[] = [];
let hydrated = false;
const listeners = new Set<() => void>();

const emit = () => {
  for (const listener of listeners) listener();
  void saveJson(STORAGE_KEY, lines);
};

// One hydration at module load; emits only if something was stored.
void loadJson<CartLine[]>(STORAGE_KEY).then(stored => {
  hydrated = true;
  if (stored?.length) {
    lines = stored;
    for (const listener of listeners) listener();
  }
});

export function addToCart(product: ProductCardData, qty = 1): void {
  const existing = lines.find(line => line.product.id === product.id);
  lines = existing
    ? lines.map(line =>
        line.product.id === product.id
          ? // Refresh the snapshot too: the price shown in the cart should
            // be the one the buyer just saw on the product page.
            { product, qty: line.qty + qty }
          : line
      )
    : [...lines, { product, qty }];
  emit();
}

export function setQty(productId: string, qty: number): void {
  lines =
    qty <= 0
      ? lines.filter(line => line.product.id !== productId)
      : lines.map(line =>
          line.product.id === productId ? { ...line, qty } : line
        );
  emit();
}

export function removeLine(productId: string): void {
  lines = lines.filter(line => line.product.id !== productId);
  emit();
}

export function clearCart(): void {
  lines = [];
  emit();
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

/** Reactive view of the cart for any component. */
export function useCart(): { lines: CartLine[]; hydrated: boolean } {
  const snapshot = useSyncExternalStore(
    subscribe,
    () => lines,
    () => lines
  );
  return { lines: snapshot, hydrated };
}

export const cartCount = (all: CartLine[]) =>
  all.reduce((sum, line) => sum + line.qty, 0);

export const cartSubtotal = (all: CartLine[]) =>
  all.reduce((sum, line) => sum + line.product.price * line.qty, 0);
