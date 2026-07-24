import { useEffect, type PropsWithChildren } from 'react';
import { useLocation, useNavigate } from '@v-miniapp/ui-react';
import { useSession, useSessionHydrated } from '@/lib/auth';

/**
 * Route middleware: one list of paths that need a session, one redirect.
 * Pages never check auth themselves.
 *
 * Browsing stays anonymous by design (review rule 3.4.8) — this list is
 * only for screens that are meaningless without an owner. Actions inside
 * public pages (the checkout button) do their own check at the moment of
 * the action, which is the pattern the review rules prefer anyway.
 *
 * Waits for the stored session to hydrate before judging: on a cold
 * start "no session yet" usually just means "still reading storage",
 * and bouncing a logged-in user to /login would be wrong.
 */
const AUTH_REQUIRED = ['/orders', '/checkout', '/order', '/seller'];

/** What /login reads to know where to go once it succeeds. */
export type LoginTarget = {
  pathname: string;
  params?: Record<string, string>;
};

export const SessionGuardLayout = ({ children }: PropsWithChildren) => {
  const location = useLocation();
  const navigate = useNavigate();
  const session = useSession();
  const hydrated = useSessionHydrated();

  const pathname = location?.pathname ?? '/';
  const guarded = AUTH_REQUIRED.includes(pathname);
  const mustLogin = guarded && hydrated && !session;

  // Serialised so the effect below has a stable dependency — the params
  // object is a fresh identity on every render and would loop.
  const params = JSON.stringify(location?.params ?? {});

  useEffect(() => {
    if (!mustLogin) return;
    // Replace, not push: the guarded page never really opened, so the
    // back button should not return to it.
    //
    // But `replace` erases where the user was going, and the tab bar
    // replaces too — tapping the Orders tab overwrites the current entry,
    // then this overwrites that. Signing in and calling navigate(-1) then
    // lands somewhere unrelated, or nowhere at all when there is no entry
    // left underneath, stranding the user on /login. So carry the
    // destination along and let /login return to it by name.
    navigate('/login', {
      replace: true,
      state: {
        loginTarget: {
          pathname,
          params: JSON.parse(params) as Record<string, string>,
        } satisfies LoginTarget,
      },
    });
  }, [mustLogin, navigate, pathname, params]);

  // Guarded and not ready (hydrating, or about to redirect): render
  // nothing rather than flashing a screen that is about to disappear.
  if (guarded && (!hydrated || !session)) return null;

  return <>{children}</>;
};
