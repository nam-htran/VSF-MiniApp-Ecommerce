import { useEffect, useState, type PropsWithChildren } from 'react';
import {
  Icon,
  Typography,
  useLocation,
  useNavigate,
} from '@v-miniapp/ui-react';
import { setSearchQuery, useSearchQuery } from '@/lib/search-query';

/**
 * The app's own top chrome, as one app-level layout wrapping every page:
 * a floating back button on non-tab pages, a search pill in the same row
 * as V-App's ⋯ ✕ controls, and — once the page scrolls — a brand-red
 * backdrop behind the row, because the surface the chrome borrowed (the
 * red header, a product photo) has scrolled away.
 *
 * On /search the pill becomes the real input, in exactly the same spot,
 * on a plain white band — so the transition into search doesn't jump.
 * There is only ever ONE search box in the app, and it lives here.
 *
 * Geometry: left is ours, right belongs to V-App's pill — a platform
 * control that floats above every mini app and cannot be removed. The
 * right offset uses --vsf-header-padding-right where the runtime injects
 * it; the 112px fallback clears the pill the Simulator draws.
 */
const TAB_ROOTS = ['/', '/cart', '/orders', '/account'];
// No search pill — and, since the band only backs the pill, no band either.
// /product is here for the second reason: the photo runs to the top edge and
// a bar over it would only get in the way. The back button still floats.
const NO_SEARCH = ['/login', '/checkout', '/order', '/seller', '/product'];

/** Pages scroll in an inner container the library owns, not on window —
 * a capturing listener hears them all without naming the element. */
const useScrolled = (resetKey: string) => {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => setScrolled(false), [resetKey]);

  useEffect(() => {
    const onScroll = (event: Event) => {
      const target =
        event.target === document
          ? document.scrollingElement
          : (event.target as HTMLElement | null);
      if (!target) return;
      // Ignore the horizontal strips (flash sale): they have no vertical
      // range, and their scrollTop of 0 must not reset the state.
      if (target.scrollHeight - target.clientHeight < 50) return;
      setScrolled(target.scrollTop > 12);
    };
    window.addEventListener('scroll', onScroll, true);
    return () => window.removeEventListener('scroll', onScroll, true);
  }, []);

  return scrolled;
};

export const TopChromeLayout = ({ children }: PropsWithChildren) => {
  const location = useLocation();
  const navigate = useNavigate();
  const query = useSearchQuery();

  const pathname = location?.pathname ?? '/';
  const isSearchPage = pathname === '/search';
  const showBack = !TAB_ROOTS.includes(pathname);
  const showSearch = !NO_SEARCH.includes(pathname) && !isSearchPage;
  const scrolled = useScrolled(pathname);

  return (
    <>
      {children}

      {/* The band behind the chrome row. On /search it is a plain white
          navigation bar, always on; elsewhere it is brand red and fades
          in on scroll. Below the pill (z-40 vs z-50). */}
      {isSearchPage ? (
        <div
          aria-hidden
          className="fixed inset-x-0 top-0 z-40 border-b border-alias-border-subtle-01 bg-alias-background"
          style={{ height: 'var(--chrome-h)' }}
        />
      ) : (
        showSearch && (
          <div
            aria-hidden
            className={`fixed inset-x-0 top-0 z-40 bg-brand shadow-sm transition-opacity duration-200 ${
              scrolled ? 'opacity-100' : 'pointer-events-none opacity-0'
            }`}
            style={{ height: 'var(--chrome-h)' }}
          />
        )
      )}

      {showBack && (
        <button
          type="button"
          aria-label="Quay lại"
          // Leaving /search fades rather than slides: the input collapses
          // back into the pill in place, so a horizontal shove would fight
          // that. Everywhere else keeps the default reverse-slide.
          onClick={() =>
            isSearchPage
              ? navigate(-1, { animation: { type: 'fade_in' } })
              : navigate(-1)
          }
          className="fixed left-3 z-50 flex size-9 items-center justify-center rounded-full bg-alias-background/90 shadow-md backdrop-blur"
          style={{ top: 'calc(var(--safe-area-inset-top, 44px) + 8px)' }}>
          <Icon name="chevron-left" size={20} />
        </button>
      )}

      {/* The same pill frame everywhere. On /search it holds a real
          input (grey, like a field on a white bar); elsewhere it is a
          button that navigates there. Identical size and position, so
          entering search feels like the pill opening up.
          A bare <input> on purpose, against the usual components rule:
          the requirement is pixel-parity with our own pill, and the
          library's SearchField brings its own frame. */}
      {isSearchPage ? (
        <div
          className="fixed z-50 flex h-9 items-center gap-2 rounded-full bg-alias-layer-01 px-3"
          style={{
            top: 'calc(var(--safe-area-inset-top, 44px) + 8px)',
            left: showBack ? '60px' : '12px',
            right: 'var(--vsf-header-padding-right, 112px)',
          }}>
          <Icon name="magnifier" size={16} color="text-tertiary" />
          <input
            autoFocus
            value={query}
            onChange={event => setSearchQuery(event.target.value)}
            placeholder="Tìm sản phẩm, cửa hàng…"
            className="min-w-0 flex-1 bg-transparent text-sm outline-none"
          />
        </div>
      ) : (
        showSearch && (
          <button
            type="button"
            aria-label="Tìm kiếm"
            // A white pill reads well on every surface it meets: the red
            // header at rest, the red backdrop when scrolled, and product
            // photos on detail pages.
            // Fade into search instead of the global slide_left: a shove
            // from the right fights the illusion that this pill just opened
            // into the input. A fade keeps it feeling like the same spot.
            onClick={() => navigate('/search', { animation: { type: 'fade_in' } })}
            className="fixed z-50 flex h-9 items-center gap-2 rounded-full bg-alias-background/90 px-3 shadow-md backdrop-blur"
            style={{
              top: 'calc(var(--safe-area-inset-top, 44px) + 8px)',
              left: showBack ? '60px' : '12px',
              right: 'var(--vsf-header-padding-right, 112px)',
            }}>
            <Icon name="magnifier" size={16} color="text-tertiary" />
            <Typography size="small" color="text-tertiary" className="truncate">
              Tìm sản phẩm, cửa hàng…
            </Typography>
          </button>
        )
      )}
    </>
  );
};
