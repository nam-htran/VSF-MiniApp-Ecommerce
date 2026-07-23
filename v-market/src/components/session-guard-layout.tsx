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
const AUTH_REQUIRED = ['/orders', '/checkout', '/order'];

export const SessionGuardLayout = ({ children }: PropsWithChildren) => {
  const location = useLocation();
  const navigate = useNavigate();
  const session = useSession();
  const hydrated = useSessionHydrated();

  const pathname = location?.pathname ?? '/';
  const guarded = AUTH_REQUIRED.includes(pathname);
  const mustLogin = guarded && hydrated && !session;

  useEffect(() => {
    if (mustLogin) navigate('/login', { replace: true });
  }, [mustLogin, navigate]);

  // Guarded and not ready (hydrating, or about to redirect): render
  // nothing rather than flashing a screen that is about to disappear.
  if (guarded && (!hydrated || !session)) return null;

  return <>{children}</>;
};
