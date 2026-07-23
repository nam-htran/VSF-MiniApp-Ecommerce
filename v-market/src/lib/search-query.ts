import { useSyncExternalStore } from 'react';

/**
 * The search query, shared between the chrome (where the input lives on
 * /search) and the results page (which filters by it). Two component
 * trees, one value — same module-store pattern as cart and session.
 */
let query = '';
const listeners = new Set<() => void>();

export function setSearchQuery(next: string): void {
  query = next;
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
