import type { PropsWithChildren } from 'react';
import { Icon, useLocation, useNavigate } from '@v-miniapp/ui-react';

/**
 * App-level layout (IAppConfig.Layouts) — wraps every page, so the back
 * button sits in the same fixed spot everywhere without each page
 * remembering to add it.
 *
 * Hidden on tab roots: those are the bottom-bar destinations, there is
 * nothing to go back to, and a dead button is worse than none. Leaving
 * the mini app itself is V-App's ✕ button, not ours.
 *
 * Top-left on purpose — V-App's own ⋯ ✕ controls occupy the top-right.
 */
const TAB_ROOTS = ['/', '/orders', '/account'];

export const BackButtonLayout = ({ children }: PropsWithChildren) => {
  const location = useLocation();
  const navigate = useNavigate();

  const pathname = location?.pathname ?? '/';
  const showBack = !TAB_ROOTS.includes(pathname);

  return (
    <>
      {children}
      {showBack && (
        <button
          type="button"
          aria-label="Quay lại"
          onClick={() => navigate(-1)}
          className="fixed left-4 z-50 flex size-10 items-center justify-center rounded-full bg-alias-background shadow-md"
          style={{ top: 'calc(var(--safe-area-inset-top, 0px) + 12px)' }}>
          <Icon name="chevron-left" size={22} />
        </button>
      )}
    </>
  );
};
