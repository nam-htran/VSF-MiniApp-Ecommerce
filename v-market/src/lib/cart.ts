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
 *
 * A line is a product *and* the option chosen, so "Áo thun / L" and
 * "Áo thun / XL" are two lines with two quantities — they are two rows of
 * stock on the server, and merging them here would ship the wrong size.
 */
export type CartVariant = {
  id: string;
  /** "Đen / L" — what the cart row and the receipt show. */
  label: string;
  /** Set only when this option costs more than the product's price. */
  price?: number;
  imageUrl?: string | null;
};

export type CartLine = {
  product: ProductCardData;
  variant?: CartVariant;
  qty: number;
};

/** Identity of a cart row. Two sizes of one shirt are different rows. */
export const lineKey = (line: CartLine): string =>
  `${line.product.id}::${line.variant?.id ?? ''}`;

/** What one unit of this line costs, the option's price winning. */
export const linePrice = (line: CartLine): number =>
  line.variant?.price ?? line.product.price;

// v2: lines gained a variant. A cart saved before options existed could
// hold a product that now requires one, and checkout would reject it with
// "chọn phân loại" that the buyer cannot act on — so those carts are
// dropped rather than silently broken.
const STORAGE_KEY = 'cart.v2';

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

export function addToCart(
  product: ProductCardData,
  variant?: CartVariant,
  qty = 1
): void {
  const key = `${product.id}::${variant?.id ?? ''}`;
  const existing = lines.find(line => lineKey(line) === key);
  lines = existing
    ? lines.map(line =>
        lineKey(line) === key
          ? // Refresh the snapshot too: the price shown in the cart should
            // be the one the buyer just saw on the product page.
            { product, variant, qty: line.qty + qty }
          : line
      )
    : [...lines, { product, variant, qty }];
  emit();
}

export function setQty(key: string, qty: number): void {
  lines =
    qty <= 0
      ? lines.filter(line => lineKey(line) !== key)
      : lines.map(line => (lineKey(line) === key ? { ...line, qty } : line));
  emit();
}

export function removeLine(key: string): void {
  lines = lines.filter(line => lineKey(line) !== key);
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
  all.reduce((sum, line) => sum + linePrice(line) * line.qty, 0);
