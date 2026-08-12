import { useSyncExternalStore } from 'react';

/**
 * The search query, shared between the chrome (where the input lives on
 * /search) and the results page (which filters by it). Two component
 * trees, one value — same module-store pattern as cart and session.
 */
let query = '';
export type SearchFilters = {
  category?: string;
  minPrice?: number;
  maxPrice?: number;
  onSale: boolean;
  sort: 'relevance' | 'price-asc' | 'price-desc';
};

export const EMPTY_SEARCH_FILTERS: SearchFilters = {
  onSale: false,
  sort: 'relevance',
};

let filters = EMPTY_SEARCH_FILTERS;
const listeners = new Set<() => void>();

export function setSearchQuery(next: string): void {
  query = next;
  for (const listener of listeners) listener();
}

export function setSearchFilters(next: SearchFilters): void {
  filters = next;
  for (const listener of listeners) listener();
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

export function useSearchQuery(): string {
  return useSyncExternalStore(
    subscribe,
    () => query,
    () => query
  );
}

export function useSearchFilters(): SearchFilters {
  return useSyncExternalStore(
    subscribe,
    () => filters,
    () => filters
  );
}

export function searchFilterCount(value: SearchFilters): number {
  return [
    value.category,
    value.minPrice,
    value.maxPrice,
    value.onSale,
    value.sort !== 'relevance',
  ].filter(Boolean).length;
}
