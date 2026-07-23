import { IAppConfig, Icon } from '@v-miniapp/ui-react';
import { SessionGuardLayout } from './components/session-guard-layout';
import { TopChromeLayout } from './components/top-chrome-layout';
import { CartTabIcon } from './components/cart-tab-icon';
import HomePage from './pages/home-page';
import ProductPage from './pages/product-page';
import CartPage from './pages/cart-page';
import LoginPage from './pages/login-page';
import SearchPage from './pages/search-page';
import OrdersPage from './pages/orders-page';
import AccountPage from './pages/account-page';

/**
 * Routing is single-level: `/product/123` does not work, `/product?id=123`
 * does. Paths are case-sensitive, and an unregistered path silently opens
 * the home page instead of failing — so keep them lowercase and register
 * each screen here as it is built.
 *
 * See docs/day3/platform-constraints.md §3.
 */
export const getAppConfig = (): IAppConfig => ({
  // Every page passes through these, outermost first: the session guard
  // (route middleware — auth checks live there, not in pages), then the
  // top chrome (back button + search pill).
  Layouts: [SessionGuardLayout, TopChromeLayout],
  pages: [
    {
      pathname: '/',
      Component: HomePage,
      // Hidden so the promo section bleeds to the top edge. The page now
      // owns the safe area: it pads by --safe-area-inset-top itself and
      // keeps the top-right corner clear of V-App's own buttons. No back
      // button needed — this is the tab root, there is nowhere to go back.
      navigationBar: { hidden: true },
      bottomTabBarId: 'home',
    },
    {
      // Detail pages take the id as a query param — /product?id=… — the
      // router only supports single-level paths. Not a tab root, so the
      // fixed back button from BackButtonLayout appears here.
      pathname: '/product',
      Component: ProductPage,
      navigationBar: { hidden: true },
      // No bottomTabBarId — the tab bar hides itself on pages without
      // one, leaving room for this page's own fixed buy bar.
    },
    {
      pathname: '/cart',
      Component: CartPage,
      navigationBar: { hidden: true },
      bottomTabBarId: 'cart',
    },
    {
      pathname: '/search',
      Component: SearchPage,
      navigationBar: { hidden: true },
      // The tab bar only shows on pages whose bottomTabBarId matches one
      // of its items. Search is not a tab, but the bar should stay put —
      // borrowing 'home' keeps it visible (with Home highlighted).
      bottomTabBarId: 'home',
    },
    {
      // Dev-only stand-in for V-App's own sign-in; not a tab root, so the
      // floating back button appears.
      pathname: '/login',
      Component: LoginPage,
      navigationBar: { hidden: true },
    },
    {
      pathname: '/orders',
      Component: OrdersPage,
      navigationBar: { title: 'Đơn hàng', hidden: true },
      bottomTabBarId: 'orders',
    },
    {
      pathname: '/account',
      Component: AccountPage,
      navigationBar: { title: 'Tài khoản', hidden: true },
      bottomTabBarId: 'account',
    },
  ],
  animation: {
    type: 'slide_left',
  },
  pageLayout: {
    hasSpacing: false,
  },
  keepAlive: {
    enable: true,
  },
  bottomTabBar: {
    // The active tab pops: brand colour, filled icon variant, and a
    // slight lift. The inactive state stays outline and quiet.
    activeColor: 'global-teal-teal-60',
    items: [
      {
        id: 'home',
        name: 'Trang chủ',
        path: '/',
        icon: { name: 'house' },
        activeIcon: (
          <Icon name="house" type="fill" className="-translate-y-0.5 scale-110 transition-transform" />
        ),
      },
      {
        id: 'cart',
        name: 'Giỏ hàng',
        path: '/cart',
        // A live component: the config is built once, but the element
        // inside it subscribes to the cart store and shows the count.
        icon: <CartTabIcon />,
        activeIcon: <CartTabIcon active />,
      },
      {
        id: 'orders',
        name: 'Đơn hàng',
        path: '/orders',
        icon: { name: 'receipt' },
        activeIcon: (
          <Icon name="receipt" type="fill" className="-translate-y-0.5 scale-110 transition-transform" />
        ),
      },
      {
        id: 'account',
        name: 'Tài khoản',
        path: '/account',
        icon: { name: 'user' },
        activeIcon: (
          <Icon name="user" type="fill" className="-translate-y-0.5 scale-110 transition-transform" />
        ),
      },
    ],
  },
});
