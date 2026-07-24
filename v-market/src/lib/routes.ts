/**
 * The few facts about routes that more than one layout needs to agree on.
 * Kept here rather than duplicated, because when they drift the symptoms
 * are confusing: a back button on a tab, or a tab you get thrown out of.
 */

/**
 * Paths that are bottom-tab roots. Two consequences: no floating back
 * button (there is nothing behind a tab), and no redirecting away from
 * them — a tab the user just pressed has to stay where they pressed it.
 *
 * Must match the `path` of each item in `bottomTabBar` in app.config.tsx.
 */
export const TAB_ROOTS = ['/', '/cart', '/orders', '/account'];

/**
 * Screens that are meaningless without an owner. Browsing stays anonymous
 * by design (review rule 3.4.8) — this is only the list of screens that
 * are *about* the person looking at them.
 */
export const AUTH_REQUIRED = ['/orders', '/checkout', '/order', '/seller'];

/** Where /login should go once it succeeds. */
export type LoginTarget = {
  pathname: string;
  params?: Record<string, string>;
};
