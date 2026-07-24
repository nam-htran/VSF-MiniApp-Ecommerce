import { useSyncExternalStore } from 'react';
import { loadJson, saveJson } from './storage';
import type { SessionUser } from '@/api/auth';

/**
 * The V-Market session: our own JWT plus the user it belongs to. The
 * V-App access token never reaches the client — this is the only thing
 * the MiniApp holds.
 *
 * Same shape as the cart store, for the same reason: app-level Layouts
 * wrap each page separately, so context would fragment. Persisted
 * through the storage seam so a restart keeps the session, matching
 * review rule 2.4.5 (stay signed in until an explicit logout).
 */
export type Session = {
  token: string;
  user: SessionUser;
  /**
   * The V-App account this session came from. Kept so the session can be
   * renewed silently when the JWT expires — see lib/session-renew.ts.
   * Not the same as `user.id`, which is V-Market's own id.
   */
  vappUserId: string;
};

// v2 adds vappUserId. A v1 session cannot be renewed, and every v1 token
// is long expired anyway, so there is nothing worth migrating.
const STORAGE_KEY = 'session.v2';

let session: Session | null = null;
// The stored session loads asynchronously; until it has, "no session"
// means "don't know yet" — route guards must wait, not redirect.
let hydrated = false;
const listeners = new Set<() => void>();

const emit = () => {
  for (const listener of listeners) listener();
};

void loadJson<Session>(STORAGE_KEY).then(stored => {
  if (stored?.token) session = stored;
  hydrated = true;
  emit();
});

export function signIn(next: Session): void {
  session = next;
  emit();
  void saveJson(STORAGE_KEY, next);
}

export function signOut(): void {
  session = null;
  emit();
  void saveJson(STORAGE_KEY, {});
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

export function useSession(): Session | null {
  return useSyncExternalStore(
    subscribe,
    () => session,
    () => session
  );
}

/** For route guards: whether the stored session has been read yet. */
export function useSessionHydrated(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => hydrated,
    () => hydrated
  );
}

/** For API calls that need the bearer token outside React. */
export const currentToken = () => session?.token ?? null;

/** For the renewer, which needs the V-App account behind the session. */
export const currentSession = () => session;
