import { loadJson, saveJson } from './storage';

/**
 * What this device has been looking at, for a shopper with no account.
 *
 * The storefront is ranked from browsing history, and the server only has
 * one for people who signed in. A marketplace that recommends nothing until
 * you register recommends nothing to most of its visitors, so the history
 * for everyone else lives here and travels with the request that needs it.
 *
 * On the device rather than on the server: nobody who never signed in leaves
 * a browsing record behind, and clearing it is theirs to do.
 */

const KEY = 'vmarket.seen';

/** Matches HISTORY_DEPTH on the server, which trims to it anyway. */
const DEPTH = 10;

/** Oldest first, repeats kept — the order and the shape the model reads. */
let seen: string[] = [];

// Storage is async, and the first storefront request can beat it. Readers
// await this, so a cold start ranks from the history the device already had
// instead of looking like a first-ever visit.
const hydrated = loadJson<string[]>(KEY).then(stored => {
  if (Array.isArray(stored)) seen = stored.slice(-DEPTH);
});

/** Repeats are not collapsed: looking at one product four times says
 *  something a deduplicated list would lose. */
export const rememberSeen = (productId: string): void => {
  seen = [...seen, productId].slice(-DEPTH);
  void saveJson(KEY, seen);
};

export const seenProducts = async (): Promise<string[]> => {
  await hydrated;
  return seen;
};
