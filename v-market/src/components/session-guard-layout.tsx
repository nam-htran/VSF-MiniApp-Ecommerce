import { useEffect, type PropsWithChildren } from 'react';
import { useLocation, useNavigate, type IIconName } from '@v-miniapp/ui-react';
import { useSession, useSessionHydrated } from '@/lib/auth';
import { AUTH_REQUIRED, TAB_ROOTS, type LoginTarget } from '@/lib/routes';
import { SignInRequired } from './sign-in-required';

/**
 * Route middleware: one list of paths that need a session, and two ways
 * of asking for one. Pages never check auth themselves.
 *
 * Browsing stays anonymous by design (review rule 3.4.8) — AUTH_REQUIRED
 * is only for screens that are meaningless without an owner. Actions
 * inside public pages (the checkout button) do their own check at the
 * moment of the action, which is the pattern the review rules prefer.
 *
 * Waits for the stored session to hydrate before judging: on a cold
 * start "no session yet" usually just means "still reading storage",
 * and bouncing a logged-in user to /login would be wrong.
 */

/** Copy for the tab roots that need an account. */
const TAB_PROMPT: Record<
  string,
  { icon: IIconName; title: string; message: string }
> = {
  '/orders': {
    icon: 'receipt',
    title: 'Đăng nhập để xem đơn hàng',
    message:
      'Đơn hàng gắn với tài khoản V-App của bạn — đăng nhập để xem đơn đã đặt và theo dõi giao hàng.',
  },
};

export const SessionGuardLayout = ({ children }: PropsWithChildren) => {
  const location = useLocation();
  const navigate = useNavigate();
  const session = useSession();
  const hydrated = useSessionHydrated();

  const pathname = location?.pathname ?? '/';
  const guarded = AUTH_REQUIRED.includes(pathname);
  const missing = guarded && hydrated && !session;

  // A tab root asks in place; anything else redirects. Throwing someone
  // off a tab they just pressed — and off the tab bar with it — reads as
  // being ejected from the app, not as being asked to sign in.
  const askHere = missing && TAB_ROOTS.includes(pathname);
  const mustLogin = missing && !askHere;

  // Serialised so the effect below has a stable dependency — the params
  // object is a fresh identity on every render and would loop.
  const params = JSON.stringify(location?.params ?? {});

  useEffect(() => {
    if (!mustLogin) return;
    // Replace, not push: the guarded page never really opened, so the
    // back button should not return to it.
    //
    // But `replace` erases where the user was going, and the tab bar
    // replaces too — so signing in and calling navigate(-1) can land
    // somewhere unrelated, or nowhere at all when no entry is left
    // underneath. Carry the destination and let /login return to it.
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

  if (askHere) {
    const prompt = TAB_PROMPT[pathname];
    return prompt ? (
      <SignInRequired target={{ pathname }} {...prompt} />
    ) : null;
  }

  // Guarded and not ready (hydrating, or about to redirect): render
  // nothing rather than flashing a screen that is about to disappear.
  if (guarded && (!hydrated || !session)) return null;

  return <>{children}</>;
};
